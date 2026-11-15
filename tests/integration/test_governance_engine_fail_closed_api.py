"""
Dispatcher-level fail-closed test for the acgs-lite layer.

Drives the real ``backend.main.app`` (Auth -> RBAC -> GovernanceMiddleware)
with a real ACGSIntegration singleton, not a mocked governance object. The
constitution only blocks "harm|kill", so the rules engine alone ALLOWS the
request; only a dead acgs-lite engine can turn it into a governance 403.
"""

import pytest
from fastapi.testclient import TestClient

import backend.governance.acgs_integration as acgs_integration
from backend.main import app
from tests.integration.test_api_auth import (  # noqa: F401  (fixtures)
    _bearer,
    auth_env,
    db_calls,
    make_token,
    rsa_keys,
)

pytestmark = [pytest.mark.integration, pytest.mark.governance]

DOMAINS = "/api/v1/recommendations/domains"
GOVERNANCE_BLOCKED = "Operation blocked by governance rules"
CONSTITUTION = """
rules:
  - id: block-harm
    pattern: "harm|kill"
    severity: CRITICAL
    action: BLOCK
    description: "Block harmful operations"
    maci_phase: MONITOR
"""


@pytest.fixture
def constitution(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(CONSTITUTION)
    return path


@pytest.fixture
def client(auth_env, db_calls) -> TestClient:  # noqa: F811
    return TestClient(app, raise_server_exceptions=False)


def _get_domains(client, make_token):  # noqa: F811
    return client.get(DOMAINS, headers=_bearer(make_token(role="viewer")))


def test_engine_init_failure_denies_request(
    client, make_token, constitution, monkeypatch, caplog  # noqa: F811
):
    # Same failure point with or without acgs-lite installed: the builder is
    # stubbed, so engine construction is what raises.
    monkeypatch.setattr(acgs_integration, "ACGS_AVAILABLE", True)
    monkeypatch.setattr(acgs_integration, "ACGS_IMPORT_ERROR", None)
    monkeypatch.setattr(
        acgs_integration,
        "build_acgs_constitution",
        lambda path: object(),
        raising=False,
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("engine construction failed")

    monkeypatch.setattr(acgs_integration, "GovernanceEngine", _raise, raising=False)
    acgs_integration.initialize_governance(constitution_path=str(constitution))
    assert "engine construction failed" in caplog.text

    response = _get_domains(client, make_token)

    assert response.status_code == 403
    body = response.json()
    assert body["detail"] == GOVERNANCE_BLOCKED
    assert any(v["rule_id"] == "acgs-engine-unavailable" for v in body["violations"])
    assert "engine construction failed" not in response.text


def test_same_request_is_not_governance_blocked_when_engine_is_healthy(
    client, make_token, constitution  # noqa: F811
):
    """Control: without the forced failure the request passes governance."""
    acgs_integration.initialize_governance(constitution_path=str(constitution))

    response = _get_domains(client, make_token)

    assert response.status_code == 200, response.text
    assert response.headers["X-Governance-Decision"] == "ALLOW"
