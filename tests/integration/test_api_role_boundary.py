"""
End-to-end role boundary: an admin edit is committed, a viewer cannot mutate.

A denial-only test also passes when every caller is wrongly treated as a
viewer, so each denial here is paired with a success that uses the same route
and the same token machinery. Tokens go through the real AuthMiddleware and
RBACMiddleware (no mocked validation or permission check). The database is a
stateful fake holding one real ``Task``; "persisted" means the values the
service passed to ``commit()``. Governance is stubbed to ALLOW so the role
policy is the only 403 source.
"""

import time
import uuid
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timezone
from fastapi.testclient import TestClient

import backend.middleware.governance_interceptor as governance_interceptor
from backend.database import get_db
from backend.main import app
from backend.models.task import Task
from tests.integration.test_api_auth import (  # noqa: F401  (fixtures)
    AUDIENCE,
    CRED_ERROR,
    ISSUER,
    _MISSING,
    _bearer,
    auth_env,
    make_token,
    rsa_keys,
)

pytestmark = pytest.mark.integration

TASK_ID = "00000000-0000-0000-0000-0000000000aa"
TASK_URL = f"/api/v1/tasks/{TASK_ID}"
ORIGINAL_TITLE = "original title"
NEW_TITLE = "edited by an authorized caller"
INSUFFICIENT = {"detail": "Insufficient permissions"}
SPA_CLIENT_ID = "acgs-enterprise-manager-spa"

# Values that must never grant more than viewer (exact lowercase strings only).
UNSUPPORTED_ROLE_VALUES = [
    "Admin",
    "ADMIN",
    " admin",
    "superuser",
    ["admin"],
    {"role": "admin"},
    None,
    1,
    True,
]


class FakeTaskStore:
    """One real Task, plus a record of every session opened and every commit."""

    def __init__(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.task = Task(
            id=uuid.UUID(TASK_ID),
            title=ORIGINAL_TITLE,
            description=None,
            status="todo",
            priority="medium",
            tags=[],
            created_at=now,
            updated_at=now,
        )
        self.sessions: List[Any] = []
        self.commits: List[Dict[str, Any]] = []
        self.deleted: List[Any] = []

    async def session(self):
        session = AsyncMock()
        session.add = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = self.task

        async def _execute(*_args, **_kwargs):
            return result

        async def _commit():
            self.commits.append({"title": self.task.title, "status": self.task.status})

        async def _delete(obj):
            self.deleted.append(obj)

        session.execute.side_effect = _execute
        session.commit.side_effect = _commit
        session.delete.side_effect = _delete
        self.sessions.append(session)
        yield session


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
def store():
    store = FakeTaskStore()
    app.dependency_overrides[get_db] = store.session
    yield store
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(auth_env, store) -> TestClient:  # noqa: F811
    return TestClient(app, raise_server_exceptions=False)


def _edit(client: TestClient, headers: Dict[str, str]):
    return client.put(TASK_URL, json={"title": NEW_TITLE}, headers=headers)


def _assert_unchanged(store: FakeTaskStore, allow_governance) -> None:
    # No DB session was opened, so nothing could be written; governance (and
    # its audit/approval side effects) was never consulted.
    assert store.sessions == []
    assert store.commits == []
    assert store.deleted == []
    assert store.task.title == ORIGINAL_TITLE
    allow_governance.validate_operation.assert_not_called()


# --------------------------------------------------------------------------
# Admin succeeds, viewer is denied (same route, same token machinery)
# --------------------------------------------------------------------------


def test_admin_edit_succeeds_and_is_committed(client, make_token, store):  # noqa: F811
    response = _edit(client, _bearer(make_token(role="admin")))

    assert response.status_code == 200, response.text
    assert response.json()["title"] == NEW_TITLE
    assert store.commits == [{"title": NEW_TITLE, "status": "todo"}]


def test_admin_delete_succeeds_and_is_committed(
    client, make_token, store
):  # noqa: F811
    response = client.delete(TASK_URL, headers=_bearer(make_token(role="admin")))

    assert response.status_code == 204, response.text
    assert store.deleted == [store.task]
    assert len(store.commits) == 1


def test_viewer_edit_is_denied_and_nothing_changes(
    client, make_token, store, allow_governance  # noqa: F811
):
    response = _edit(client, _bearer(make_token(role="viewer")))

    assert response.status_code == 403
    assert response.json() == INSUFFICIENT
    _assert_unchanged(store, allow_governance)


def test_viewer_delete_is_denied_and_nothing_changes(
    client, make_token, store, allow_governance  # noqa: F811
):
    response = client.delete(TASK_URL, headers=_bearer(make_token(role="viewer")))

    assert response.status_code == 403
    _assert_unchanged(store, allow_governance)


def test_user_role_may_edit_but_not_delete(
    client, make_token, store, allow_governance  # noqa: F811
):
    # "user" is a real editing role, not a viewer: edits pass, deletes need manager.
    token = make_token(role="user")
    assert _edit(client, _bearer(token)).status_code == 200
    assert store.commits == [{"title": NEW_TITLE, "status": "todo"}]

    response = client.delete(TASK_URL, headers=_bearer(token))
    assert response.status_code == 403
    assert store.deleted == []


def test_reindex_needs_admin_not_manager(
    client, make_token, store, allow_governance  # noqa: F811
):
    # The only admin-only route: proves "admin" is distinguished from "manager".
    url = "/api/v1/search/reindex"
    response = client.post(url, headers=_bearer(make_token(role="manager")))
    assert response.status_code == 403
    assert response.json() == INSUFFICIENT
    assert store.sessions == []

    response = client.post(url, headers=_bearer(make_token(role="admin")))
    assert response.status_code not in (401, 403), response.text
    assert len(store.sessions) == 1  # reached the handler


# --------------------------------------------------------------------------
# Valid token, unusable role -> viewer fallback (authenticated, read-only)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("role", [_MISSING, *UNSUPPORTED_ROLE_VALUES], ids=repr)
def test_missing_or_unsupported_role_falls_back_to_viewer(
    client, make_token, store, allow_governance, role  # noqa: F811
):
    token = make_token(role=role)

    response = _edit(client, _bearer(token))
    assert response.status_code == 403
    assert response.json() == INSUFFICIENT
    _assert_unchanged(store, allow_governance)

    # Still authenticated: viewer reads work (fallback, not rejection).
    read = client.get(TASK_URL, headers=_bearer(token))
    assert read.status_code == 200, read.text
    assert read.json()["title"] == ORIGINAL_TITLE


# --------------------------------------------------------------------------
# ID token vs access token
# --------------------------------------------------------------------------


def _id_token(make_token, **overrides):  # noqa: F811
    # Shape of an OIDC ID token: audience is the SPA client id, carries a nonce.
    claims = {"aud": SPA_CLIENT_ID, "nonce": "n-123", "role": "admin"}
    claims.update(overrides)
    return make_token(**claims)


def test_access_token_without_role_gets_no_admin_even_if_id_token_has_it(
    client, make_token, store, allow_governance  # noqa: F811
):
    # The ID token (which may say "admin") is never sent to the API; the API
    # sees only this access token, which carries no role -> viewer.
    access_token = make_token(role=_MISSING)

    response = _edit(client, _bearer(access_token))
    assert response.status_code == 403
    _assert_unchanged(store, allow_governance)


def test_id_token_as_bearer_is_rejected(
    client, make_token, store, allow_governance  # noqa: F811
):
    # Rejected by audience (aud = SPA client id, not AUTH_JWT_AUDIENCE). The
    # API does not rely on "typ": many IdPs label both token kinds "JWT".
    for method in ("GET", "PUT"):
        response = client.request(
            method,
            TASK_URL,
            json={"title": NEW_TITLE},
            headers=_bearer(_id_token(make_token)),
        )
        assert response.status_code == 401
        assert response.json() == CRED_ERROR
    _assert_unchanged(store, allow_governance)


# --------------------------------------------------------------------------
# Invalid tokens are rejected outright, never downgraded to viewer
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def foreign_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _invalid_admin_tokens(make_token, foreign_key) -> Dict[str, str]:  # noqa: F811
    now = int(time.time())
    admin_claims = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "role": "admin",
    }
    foreign = jwt.encode(admin_claims, foreign_key, algorithm="RS256")
    viewer = make_token(role="viewer").split(".")
    return {
        "invalid_signature": foreign,
        "untrusted_issuer": make_token(role="admin", iss="https://evil.example/"),
        "wrong_audience": make_token(role="admin", aud="another-api"),
        "expired": make_token(role="admin", iat=now - 3600, exp=now - 120),
        # Viewer token whose payload was edited to "admin" (e.g. a client that
        # rewrote its stored token): signature no longer matches.
        "role_tampered": ".".join([viewer[0], foreign.split(".")[1], viewer[2]]),
    }


@pytest.mark.parametrize(
    "case",
    [
        "invalid_signature",
        "untrusted_issuer",
        "wrong_audience",
        "expired",
        "role_tampered",
    ],
)
@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_invalid_token_is_rejected_not_viewer(
    client, make_token, foreign_key, store, allow_governance, case, method  # noqa: F811
):
    token = _invalid_admin_tokens(make_token, foreign_key)[case]
    response = client.request(
        method, TASK_URL, json={"title": NEW_TITLE}, headers=_bearer(token)
    )

    # 401 even for a read: an invalid token never becomes viewer access.
    assert response.status_code == 401
    assert response.json() == CRED_ERROR
    assert response.headers.get("www-authenticate") == "Bearer"
    _assert_unchanged(store, allow_governance)
