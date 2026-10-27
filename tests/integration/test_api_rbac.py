"""
Integration tests for route authorization (backend.auth.policy).

Drives the real ``backend.main.app`` with tokens minted by the fixtures in
test_api_auth.py. Governance is stubbed to ALLOW so the only 403 source on
these routes is the role policy.
"""

from typing import List, Tuple
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import backend.middleware.governance_interceptor as governance_interceptor
from backend.auth.dependencies import ROLE_HIERARCHY, get_current_user
from backend.api import tasks
from backend.auth.policy import ROUTE_POLICY, enforce_route_policy
from backend.database import get_db
from backend.main import API_AUTH_DEPENDENCIES, app, create_app
from backend.middleware.auth import AuthMiddleware
from tests.integration.test_api_auth import (  # noqa: F401  (fixtures)
    _MISSING,
    _bearer,
    _concrete_path,
    auth_env,
    db_calls,
    make_token,
    rsa_keys,
)

pytestmark = pytest.mark.integration

INSUFFICIENT = {"detail": "Insufficient permissions"}
ROLES_BY_RANK = sorted(ROLE_HIERARCHY, key=ROLE_HIERARCHY.get)


def _api_route_methods() -> List[Tuple[str, str]]:
    pairs = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/"):
            for method in sorted(route.methods):
                pairs.append((method, route.path))
    return pairs


def _role_below(role: str) -> str:
    return ROLES_BY_RANK[ROLES_BY_RANK.index(role) - 1]


@pytest.fixture(autouse=True)
def allow_governance(monkeypatch):
    governance = MagicMock()
    governance.validate_operation.return_value = {
        "action": "ALLOW",
        "violations": [],
        "decision_id": "d-test",
    }
    monkeypatch.setattr(governance_interceptor, "get_governance", lambda: governance)
    return governance


@pytest.fixture
def client(auth_env, db_calls) -> TestClient:  # noqa: F811
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def call(client, make_token):  # noqa: F811
    def _do(method: str, path: str, role):
        token = make_token(role=role)
        return client.request(method, _concrete_path(path), headers=_bearer(token))

    return _do


# --------------------------------------------------------------------------
# Table coverage
# --------------------------------------------------------------------------


def test_every_api_route_has_a_policy_entry():
    pairs = _api_route_methods()
    assert len(pairs) >= 50  # guard against vacuous pass
    missing = [pair for pair in pairs if pair not in ROUTE_POLICY]
    assert missing == []


def test_no_stale_policy_entries():
    live = set(_api_route_methods())
    stale = [key for key in ROUTE_POLICY if key not in live]
    assert stale == []


def test_every_policy_value_is_a_valid_role():
    invalid = {k: v for k, v in ROUTE_POLICY.items() if v not in ROLE_HIERARCHY}
    assert invalid == {}


def _approved_minimum(method: str, path: str) -> str:
    """The user-approved policy, restated independently of the table."""
    if method == "GET":
        return "viewer"
    if (method, path) == ("POST", "/api/v1/search/reindex"):
        return "admin"
    if method == "DELETE" or path.startswith("/api/v1/financial/"):
        return "manager"
    return "user"


def test_policy_table_matches_approved_rules():
    # The matrix below is generated from the table, so it cannot catch a
    # lowered entry; this independent restatement can.
    mismatched = {
        key: (role, _approved_minimum(*key))
        for key, role in ROUTE_POLICY.items()
        if role != _approved_minimum(*key)
    }
    assert mismatched == {}


def test_every_api_route_authenticates_then_authorizes():
    wrong = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            calls = [d.call for d in route.dependant.dependencies]
            if get_current_user not in calls or enforce_route_policy not in calls:
                wrong.append(route.path)
            elif calls.index(get_current_user) > calls.index(enforce_route_policy):
                wrong.append(route.path)
    assert wrong == []


# --------------------------------------------------------------------------
# Role matrix, generated from ROUTE_POLICY itself
# --------------------------------------------------------------------------

POLICY_CASES = [
    pytest.param(method, path, role, id=f"{method} {path} >= {role}")
    for (method, path), role in sorted(ROUTE_POLICY.items())
]


@pytest.mark.parametrize("method, path, minimum", POLICY_CASES)
def test_role_just_below_minimum_is_forbidden(call, method, path, minimum):
    if minimum == ROLES_BY_RANK[0]:
        pytest.skip("minimum is the lowest role")
    response = call(method, path, _role_below(minimum))
    assert response.status_code == 403
    assert response.json() == INSUFFICIENT


@pytest.mark.parametrize("method, path, minimum", POLICY_CASES)
def test_minimum_role_passes_authorization(call, method, path, minimum):
    response = call(method, path, minimum)
    # The handler may 404/422/500 on mocked data; only authz matters here.
    assert response.status_code not in (401, 403), response.text


# --------------------------------------------------------------------------
# Spot checks
# --------------------------------------------------------------------------

TASK = "/api/v1/tasks/{task_id}"
FIN = "/api/v1/financial/{record_id}"


@pytest.mark.parametrize(
    "method, path, role, allowed",
    [
        ("GET", "/api/v1/financial/", "viewer", True),
        ("POST", "/api/v1/tasks/", "viewer", False),
        ("POST", "/api/v1/tasks/", "user", True),
        ("DELETE", TASK, "user", False),
        ("DELETE", TASK, "manager", True),
        ("POST", "/api/v1/financial/", "user", False),
        ("POST", FIN + "/approve", "manager", True),
        ("POST", "/api/v1/search/reindex", "manager", False),
        ("POST", "/api/v1/search/reindex", "admin", True),
    ],
)
def test_spot_checks(call, method, path, role, allowed):
    response = call(method, path, role)
    if allowed:
        assert response.status_code not in (401, 403), response.text
    else:
        assert response.status_code == 403
        assert response.json() == INSUFFICIENT


def test_missing_role_claim_is_viewer(call, db_calls):  # noqa: F811
    response = call("POST", "/api/v1/tasks/", _MISSING)
    assert response.status_code == 403
    assert response.json() == INSUFFICIENT
    assert db_calls == []
    assert call("GET", "/api/v1/tasks/", _MISSING).status_code not in (401, 403)


@pytest.mark.parametrize("minimum", ["user", "manager", "admin"])
def test_403_does_not_reveal_required_role(call, minimum):
    method, path = next(k for k, v in sorted(ROUTE_POLICY.items()) if v == minimum)
    response = call(method, path, "viewer")
    assert response.status_code == 403
    for role in ROLE_HIERARCHY:
        assert role not in response.text.lower()


def test_route_without_policy_entry_is_forbidden_even_for_admin(
    auth_env, make_token, caplog  # noqa: F811
):
    router = APIRouter()

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    test_app = create_app()
    test_app.include_router(
        router, prefix="/api/v1/rbac-test-only", dependencies=API_AUTH_DEPENDENCIES
    )
    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.get(
        "/api/v1/rbac-test-only/ping", headers=_bearer(make_token(role="admin"))
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Forbidden"}
    assert any(
        r.levelname == "ERROR" and "/api/v1/rbac-test-only/ping" in r.getMessage()
        for r in caplog.records
    )
    # The shared app is untouched.
    assert ("GET", "/api/v1/rbac-test-only/ping") not in _api_route_methods()


# --------------------------------------------------------------------------
# Middleware layer: RBAC runs before governance
# --------------------------------------------------------------------------

GENERATE = "/api/v1/recommendations/generate"


def test_middleware_stack_order():
    names = [m.cls.__name__ for m in app.user_middleware]  # outermost first
    assert names == [
        "BaseHTTPMiddleware",  # request timing
        "CORSMiddleware",
        "AuthMiddleware",
        "RBACMiddleware",
        "GovernanceMiddleware",
    ]


@pytest.mark.parametrize("action", ["REQUIRE_APPROVAL", "BLOCK"])
def test_denied_request_never_reaches_governance(call, allow_governance, action):
    allow_governance.validate_operation.return_value = {
        "action": action,
        "violations": ["secret-violation"],
        "decision_id": "d-secret",
    }
    response = call("POST", GENERATE, "viewer")
    assert response.status_code == 403
    assert response.json() == INSUFFICIENT  # no violations / decision_id
    allow_governance.validate_operation.assert_not_called()
    allow_governance.request_approval.assert_not_called()


def test_allowed_request_reaches_governance(call, allow_governance):
    response = call("POST", GENERATE, "user")
    assert response.status_code not in (401, 403), response.text
    allow_governance.validate_operation.assert_called_once()


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/api/v1/recommendations/does-not-exist"),
        ("POST", "/api/v1/recommendations/does-not-exist"),
        ("PUT", GENERATE),  # PARTIAL match: path exists, method does not
        ("HEAD", "/api/v1/tasks/"),  # APIRoute has no HEAD: no FULL match
        ("GET", "/api/v1"),
    ],
)
def test_unmatched_api_request_is_forbidden_for_admin(
    call, allow_governance, method, path
):
    response = call(method, path, "admin")
    assert response.status_code == 403
    if method != "HEAD":
        assert response.json() == {"detail": "Forbidden"}
    allow_governance.validate_operation.assert_not_called()
    allow_governance.request_approval.assert_not_called()


def test_denial_is_logged_without_token(client, make_token, caplog):  # noqa: F811
    token = make_token(role="viewer", sub="viewer-42")
    response = client.post(GENERATE, headers=_bearer(token))
    assert response.status_code == 403
    denials = [
        r.getMessage()
        for r in caplog.records
        if r.levelname == "WARNING" and "Authorization denied" in r.getMessage()
    ]
    assert len(denials) == 1
    assert "viewer-42" in denials[0]
    assert "POST" in denials[0] and GENERATE in denials[0]
    assert token not in caplog.text


def test_dependency_alone_enforces_policy(auth_env, make_token):  # noqa: F811
    """Defence in depth: without RBACMiddleware the route dependency still
    refuses, using the same decision function."""

    async def _fake_db():
        yield MagicMock()

    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)
    test_app.include_router(
        tasks.router, prefix="/api/v1/tasks", dependencies=API_AUTH_DEPENDENCIES
    )
    test_app.dependency_overrides[get_db] = _fake_db
    client = TestClient(test_app, raise_server_exceptions=False)
    denied = client.post("/api/v1/tasks/", headers=_bearer(make_token(role="viewer")))
    assert denied.status_code == 403
    assert denied.json() == INSUFFICIENT
    allowed = client.post("/api/v1/tasks/", headers=_bearer(make_token(role="user")))
    assert allowed.status_code not in (401, 403)


# --------------------------------------------------------------------------
# Malformed role claims map to viewer
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role",
    [["admin"], 3, {"admin": 1}, "Admin", " admin", "admin ", True, None],
    ids=repr,
)
def test_non_canonical_role_claims_cannot_reindex(call, role):
    response = call("POST", "/api/v1/search/reindex", role)
    assert response.status_code == 403
    assert response.json() == INSUFFICIENT
