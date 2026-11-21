"""
Dispatcher-level governance tests.

Every request goes through the real ``backend.main.app`` (AuthMiddleware ->
RBAC -> GovernanceMiddleware -> handler) with real governance and the shipped
constitution. Governance is never stubbed (no ``allow_governance``); only what
the recommender returns is stubbed.
"""

from pathlib import Path

import pytest

import backend.governance.acgs_integration as acgs_integration
from backend.ai.recommendation_engine import RecommendationDomain, RecommendationEngine
from backend.api import recommendations
from tests.integration._auth_helpers import _bearer

pytestmark = pytest.mark.integration

SHIPPED_CONSTITUTION = (
    Path(__file__).resolve().parents[2] / "config" / "governance_rules.yaml"
)
GENERATE = "/api/v1/recommendations/generate"
PAYLOAD = {"domain": "tasks", "entity_id": "task-1", "context": {}}


@pytest.fixture(autouse=True)
def fresh_recommendation_engine(monkeypatch):
    # The autouse isolated_audit_dir fixture already resets the governance
    # singleton; the engine caches the governance instance it was built with.
    monkeypatch.setattr(recommendations, "_recommendation_engine", None)


def use_constitution(monkeypatch, path: Path) -> acgs_integration.ACGSIntegration:
    governance = acgs_integration.ACGSIntegration(constitution_path=str(path))
    monkeypatch.setattr(acgs_integration, "_governance_instance", governance)
    return governance


@pytest.fixture
def user_headers(make_token):
    return _bearer(make_token(role="user"))


class StubRecommender:
    """Stands in for the model only; governance stays real."""

    def __init__(self):
        # entity_id -> (confidence, rationale)
        self.outputs = {}
        self.top = []

    async def recommend(self, entity_id, context):
        confidence, rationale = self.outputs.get(entity_id, (0.9, "Due soon"))
        return {
            "suggestion": f"secret-suggestion-{entity_id}",
            "confidence": confidence,
            "rationale": rationale,
            "metadata": {},
        }

    async def get_top_recommendations(self, limit, min_confidence):
        return [dict(rec) for rec in self.top]


def install_recommender(monkeypatch) -> StubRecommender:
    """Build the engine on the live governance singleton, stub only the model."""
    engine = RecommendationEngine(
        governance_integration=acgs_integration.get_governance()
    )
    stub = StubRecommender()
    engine.recommenders[RecommendationDomain.TASKS] = stub
    monkeypatch.setattr(recommendations, "_recommendation_engine", engine)
    return stub


@pytest.fixture
def recommender(monkeypatch) -> StubRecommender:
    return install_recommender(monkeypatch)


def audit_entries():
    return acgs_integration.get_governance().inspect_audit_trail(limit=1000)


def stages(entries):
    return [e["context"].get("stage") for e in entries]


def test_generate_high_confidence_is_allowed(
    client, user_headers, db_calls, recommender
):
    response = client.post(GENERATE, json=PAYLOAD, headers=user_headers)

    assert response.status_code == 201, response.text
    assert response.headers["X-Governance-Decision"] == "ALLOW"
    assert response.json()["status"] == "approved"
    assert len(db_calls) == 1
    db_calls[0].add.assert_called_once()

    entries = audit_entries()
    assert sorted(stages(entries)) == ["output", "request"]
    request_entry = next(e for e in entries if e["context"]["stage"] == "request")
    assert request_entry["operation"] == f"POST {GENERATE}"
    output_entry = next(e for e in entries if e["context"]["stage"] == "output")
    assert output_entry["operation"] == "generate_recommendation_tasks"
    assert "ai-recommendation-threshold" in (
        output_entry["validation_result"]["matched_rules"]
    )


@pytest.mark.parametrize(
    "confidence, rationale", [(0.5, "Due soon"), (0.9, ""), (0.9, "   ")]
)
def test_generate_blocked_output_is_403_and_not_stored(
    client, user_headers, db_calls, recommender, confidence, rationale
):
    recommender.outputs["task-1"] = (confidence, rationale)

    response = client.post(GENERATE, json=PAYLOAD, headers=user_headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Recommendation blocked by governance policy"}
    assert "secret-suggestion" not in response.text
    for session in db_calls:
        session.add.assert_not_called()
    output_entry = next(e for e in audit_entries() if e["context"]["stage"] == "output")
    assert output_entry["validation_result"]["action"] == "BLOCK"


def test_batch_returns_only_allowed_items(client, user_headers, recommender):
    recommender.outputs.update(
        {"low": (0.5, "weak"), "edge": (0.75, "ok"), "high": (0.95, "strong")}
    )

    response = client.post(
        "/api/v1/recommendations/batch",
        json={"domain": "tasks", "entity_ids": ["low", "edge", "high"]},
        headers=user_headers,
    )

    assert response.status_code == 200, response.text
    assert [r["entity_id"] for r in response.json()] == ["edge", "high"]
    assert "secret-suggestion-low" not in response.text
    assert "below threshold" not in response.text
    request_entry = next(
        e for e in audit_entries() if e["context"]["stage"] == "request"
    )
    assert request_entry["context"]["batch_size"] == 3
    assert stages(audit_entries()).count("output") == 3


def test_oversized_batch_is_blocked_at_request(
    client, user_headers, db_calls, recommender
):
    response = client.post(
        "/api/v1/recommendations/batch",
        json={"domain": "tasks", "entity_ids": [f"t{i}" for i in range(1001)]},
        headers=user_headers,
    )

    assert response.status_code == 403
    assert [v["rule_id"] for v in response.json()["violations"]] == ["bulk-operations"]
    assert db_calls == []
    assert stages(audit_entries()) == ["request"]


def test_top_filters_low_confidence_items(client, make_token, recommender):
    recommender.top = [
        {
            "entity_id": "a",
            "suggestion": "s-a",
            "confidence": 0.9,
            "rationale": "r",
            "metadata": {},
        },
        {
            "entity_id": "b",
            "suggestion": "secret-suggestion-b",
            "confidence": 0.2,
            "rationale": "r",
            "metadata": {},
        },
        {
            "entity_id": "c",
            "suggestion": "s-c",
            "confidence": 0.8,
            "rationale": "",
            "metadata": {},
        },
    ]

    response = client.get(
        "/api/v1/recommendations/top/tasks?min_confidence=0.1",
        headers=_bearer(make_token(role="viewer")),
    )

    assert response.status_code == 200, response.text
    assert [r["entity_id"] for r in response.json()] == ["a"]
    assert "secret-suggestion-b" not in response.text
    assert stages(audit_entries()).count("output") == 3


@pytest.mark.parametrize("path", ["/domains", "/stats"])
def test_read_only_routes_pass_request_stage(client, make_token, recommender, path):
    response = client.get(
        "/api/v1/recommendations" + path, headers=_bearer(make_token(role="viewer"))
    )

    assert response.status_code == 200, response.text
    assert response.headers["X-Governance-Decision"] == "ALLOW"
    assert stages(audit_entries()) == ["request"]


def test_audit_actor_is_verified_user_not_header(client, make_token, recommender):
    token = make_token(role="user", sub="verified-sub-42")

    response = client.post(
        GENERATE,
        json=PAYLOAD,
        headers={**_bearer(token), "X-Agent-ID": "spoof"},
    )

    assert response.status_code == 201, response.text
    request_entry = next(
        e for e in audit_entries() if e["context"]["stage"] == "request"
    )
    assert request_entry["agent_id"] == "verified-sub-42"
    assert request_entry["context"]["claimed_agent_id"] == "spoof"
    assert "agent_id" not in request_entry["context"]
    assert acgs_integration.get_governance().inspect_audit_trail(agent_id="spoof") == []


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("POST", GENERATE, PAYLOAD),
        (
            "POST",
            "/api/v1/recommendations/batch",
            {"domain": "tasks", "entity_ids": ["a"]},
        ),
        ("GET", "/api/v1/recommendations/top/tasks", None),
        ("GET", "/api/v1/recommendations/domains", None),
        ("GET", "/api/v1/recommendations/stats", None),
        ("GET", "/api/v1/recommendations/health", None),
    ],
)
def test_missing_constitution_blocks_every_recommendations_route(
    client, make_token, db_calls, monkeypatch, tmp_path, method, path, body
):
    use_constitution(monkeypatch, tmp_path / "missing.yaml")
    install_recommender(monkeypatch)

    response = client.request(
        method, path, json=body, headers=_bearer(make_token(role="user"))
    )

    assert response.status_code == 403
    assert [v["rule_id"] for v in response.json()["violations"]] == [
        "constitution-unavailable"
    ]
    assert db_calls == []


def test_constitution_typo_blocks_through_app(
    client, user_headers, db_calls, monkeypatch, tmp_path
):
    broken = tmp_path / "governance_rules.yaml"
    broken.write_text(
        SHIPPED_CONSTITUTION.read_text().replace(
            '    pattern: "harm|kill', '    patern: "harm|kill', 1
        )
    )
    assert broken.read_text() != SHIPPED_CONSTITUTION.read_text()
    governance = use_constitution(monkeypatch, broken)
    assert governance.rules_engine.load_error is not None

    response = client.post(GENERATE, json=PAYLOAD, headers=user_headers)

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == "Operation blocked by governance rules"
    assert [v["rule_id"] for v in body["violations"]] == ["constitution-unavailable"]
    assert db_calls == []
