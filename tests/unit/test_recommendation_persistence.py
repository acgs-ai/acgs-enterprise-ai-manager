"""
Unit tests for recommendation persistence in POST /generate.
Uses a mocked AsyncSession and FastAPI dependency overrides (no Postgres).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.ai.recommendation_engine import RecommendationDomain, RecommendationEngine
from backend.api import recommendations as api
from backend.database import get_db
from backend.models.recommendation import Recommendation


class StubRecommender:
    async def recommend(self, entity_id, context):
        return {
            "suggestion": "Set priority to 'high'",
            "confidence": 0.876,
            "rationale": "Due soon",
            "metadata": {"priority_score": 0.9},
        }


class StubGovernance:
    def __init__(self, action):
        self.action = action

    def validate_operation(self, operation, context):
        return {"action": self.action, "violations": ["secret-rule-detail"]}


def make_engine(action):
    engine = RecommendationEngine(governance_integration=StubGovernance(action))
    engine.recommenders[RecommendationDomain.TASKS] = StubRecommender()
    return engine


def make_session():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


def make_client(action="ALLOW", session=None):
    session = session or make_session()
    app = FastAPI()
    app.include_router(api.router, prefix="/recommendations")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[api.get_recommendation_engine] = lambda: make_engine(
        action
    )
    return TestClient(app, raise_server_exceptions=False), session


PAYLOAD = {"domain": "tasks", "entity_id": "task-42", "context": {}}


@pytest.mark.unit
def test_stored_row_fields():
    client, session = make_client("ALLOW")
    resp = client.post("/recommendations/generate", json=PAYLOAD)
    assert resp.status_code == 201

    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, Recommendation)
    assert row.domain == "tasks"
    assert row.entity_type == "tasks"
    assert row.entity_id == "task-42"
    assert row.suggestion == "Set priority to 'high'"
    assert row.confidence == 0.88
    assert row.rationale == "Due soon"
    assert row.status == "approved"
    assert row.recommendation_metadata == {"priority_score": 0.9}
    assert row.governance_check["action"] == "ALLOW"
    assert row.generated_at is not None
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(row)


@pytest.mark.unit
def test_response_returns_stored_id():
    client, session = make_client("ALLOW")
    resp = client.post("/recommendations/generate", json=PAYLOAD)
    body = resp.json()
    row = session.add.call_args.args[0]
    assert body["id"] == str(row.id)
    assert uuid.UUID(body["id"])
    assert body["status"] == "approved"


@pytest.mark.unit
def test_require_approval_is_stored_as_pending_approval():
    client, session = make_client("REQUIRE_APPROVAL")
    resp = client.post("/recommendations/generate", json=PAYLOAD)
    assert resp.status_code == 201
    assert session.add.call_args.args[0].status == "pending_approval"


@pytest.mark.unit
def test_governance_blocked_is_not_stored():
    client, session = make_client("BLOCK")
    resp = client.post("/recommendations/generate", json=PAYLOAD)
    assert resp.status_code == 403
    assert "secret-rule-detail" not in resp.text
    session.add.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.unit
def test_db_error_maps_to_500_without_leaking():
    session = make_session()
    session.commit.side_effect = RuntimeError("connection to db-host:5432 refused")
    client, _ = make_client("ALLOW", session)
    resp = client.post("/recommendations/generate", json=PAYLOAD)
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to generate recommendation"
    assert "db-host" not in resp.text
    session.rollback.assert_awaited_once()


@pytest.mark.unit
def test_invalid_domain_still_400():
    client, session = make_client("ALLOW")
    resp = client.post("/recommendations/generate", json={**PAYLOAD, "domain": "nope"})
    assert resp.status_code == 400
    session.add.assert_not_called()
