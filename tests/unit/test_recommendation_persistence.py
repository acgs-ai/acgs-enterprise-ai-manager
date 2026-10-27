"""
Unit tests for recommendation persistence in POST /generate.
Uses a mocked AsyncSession and FastAPI dependency overrides (no Postgres).
"""

import re
import uuid
from datetime import timedelta
from pathlib import Path
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


@pytest.mark.unit
def test_generated_at_is_server_utc_aware():
    client, session = make_client("ALLOW")
    resp = client.post("/recommendations/generate", json=PAYLOAD)
    assert resp.status_code == 201
    row = session.add.call_args.args[0]
    assert row.generated_at.tzinfo is not None
    assert row.generated_at.utcoffset() == timedelta(0)
    assert resp.json()["generated_at"] == row.generated_at.isoformat()


@pytest.mark.unit
def test_bad_engine_generated_at_is_not_a_400():
    class BadTimestampEngine(RecommendationEngine):
        async def generate_recommendation(self, domain, entity_id, context=None):
            return {
                "domain": "tasks",
                "entity_id": entity_id,
                "suggestion": "s",
                "confidence": 0.5,
                "rationale": "r",
                "status": "approved",
                "metadata": {},
                "generated_at": "not-a-timestamp",
            }

    session = make_session()
    app = FastAPI()
    app.include_router(api.router, prefix="/recommendations")
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[api.get_recommendation_engine] = lambda: (
        BadTimestampEngine(governance_integration=StubGovernance("ALLOW"))
    )
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/recommendations/generate", json=PAYLOAD)
    assert resp.status_code == 201


@pytest.mark.unit
def test_refresh_failure_after_commit_still_returns_201(caplog):
    session = make_session()
    session.refresh.side_effect = RuntimeError("refresh blew up")
    client, _ = make_client("ALLOW", session)
    with caplog.at_level("WARNING", logger=api.logger.name):
        resp = client.post("/recommendations/generate", json=PAYLOAD)
    assert resp.status_code == 201
    row = session.add.call_args.args[0]
    assert resp.json()["id"] == str(row.id)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    assert any("Refresh failed" in r.message for r in caplog.records)


@pytest.mark.unit
def test_model_columns_match_schema_sql():
    schema = Path(__file__).resolve().parents[2] / "database" / "schema.sql"
    sql = schema.read_text()
    block = re.search(
        r"CREATE TABLE recommendations \((.*?)\n\);", sql, re.DOTALL
    ).group(1)
    sql_columns = set()
    for line in block.splitlines():
        m = re.match(r"\s+([a-z_]+)\s+[A-Z]", line)
        if m:
            sql_columns.add(m.group(1))
    model_columns = {
        "metadata" if c.name == "recommendation_metadata" else c.name
        for c in Recommendation.__table__.columns
    }
    assert sql_columns == model_columns
