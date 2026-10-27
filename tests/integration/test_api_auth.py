"""
Integration tests for API authentication.

Drives the real ``backend.main.app`` (without its lifespan, so init_db never
runs). Tokens are minted here, in tests only: production code only verifies.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import backend.auth.dependencies as auth_deps
import backend.middleware.governance_interceptor as governance_interceptor
from backend.auth.dependencies import get_current_user, require_role
from backend.database import get_db
from backend.main import app, create_app
from backend.middleware.auth import DOCS_PATHS, PUBLIC_PATHS, AuthMiddleware

pytestmark = pytest.mark.integration

ISSUER = "https://idp.test.example/"
AUDIENCE = "acgs-enterprise-manager"
CRED_ERROR = {"detail": "Could not validate credentials"}
NOT_CONFIGURED = {"detail": "Authentication not configured"}
ALLOWED_ORIGIN = "http://localhost:3000"
JWKS_URL = "https://idp.test.example/jwks.json"
_MISSING = object()


# --------------------------------------------------------------------------
# Helpers and fixtures
# --------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _claims(**overrides: Any) -> Dict[str, Any]:
    now = int(time.time())
    claims: Dict[str, Any] = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "email": "user@example.com",
        "role": "user",
    }
    for key, value in overrides.items():
        if value is _MISSING:
            claims.pop(key, None)
        else:
            claims[key] = value
    return claims


def _unsigned_token(header: Dict[str, Any], claims: Dict[str, Any]) -> str:
    return (
        _b64url(json.dumps(header).encode())
        + "."
        + _b64url(json.dumps(claims).encode())
    )


@pytest.fixture(scope="module")
def rsa_keys() -> Tuple[Any, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_key, public_pem


def _reset_auth_caches() -> None:
    auth_deps.get_auth_settings.cache_clear()
    auth_deps._jwks_client.cache_clear()
    auth_deps._last_unknown_kid_refetch = None
    auth_deps._jwks_fetch_failed_at = None


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch, rsa_keys):
    """Configure RS256 + static PEM key auth; clear cached settings around it."""
    _, public_pem = rsa_keys
    for name in (
        "AUTH_JWKS_URL",
        "AUTH_ROLE_CLAIM",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTH_JWT_ALGORITHMS", "RS256")
    monkeypatch.setenv("AUTH_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("AUTH_JWT_KEY", public_pem)
    _reset_auth_caches()
    yield monkeypatch
    _reset_auth_caches()


@pytest.fixture
def make_token(rsa_keys):
    private_key, _ = rsa_keys

    def _make(headers: Optional[Dict[str, Any]] = None, **overrides: Any) -> str:
        return jwt.encode(
            _claims(**overrides), private_key, algorithm="RS256", headers=headers
        )

    return _make


@pytest.fixture
def db_calls():
    """Override get_db with an AsyncMock session and record handler entry."""
    calls: List[Any] = []

    async def _fake_db():
        session = AsyncMock()
        session.add = MagicMock()
        calls.append(session)
        yield session

    app.dependency_overrides[get_db] = _fake_db
    yield calls
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client(auth_env, db_calls) -> TestClient:
    # Not used as a context manager: the lifespan (init_db) never runs.
    return TestClient(app, raise_server_exceptions=False)


def _bearer(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _concrete_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", path)


def _protected_route_calls() -> List[Tuple[str, str]]:
    calls = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods or route.path in PUBLIC_PATHS:
            continue
        for method in sorted(methods):
            calls.append((method, _concrete_path(route.path)))
    return calls


def _assert_rejected(response) -> None:
    assert response.status_code == 401
    assert response.json() == CRED_ERROR
    assert response.headers.get("www-authenticate") == "Bearer"


def _raw_asgi_get(path: str, headers: Optional[List[Tuple[bytes, bytes]]] = None):
    """Send a request with an un-normalized path straight to the ASGI app."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": headers or [(b"host", b"testserver")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    messages: List[Dict[str, Any]] = []

    async def run() -> None:
        request_sent = False
        response_complete = asyncio.Event()

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await response_complete.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.body" and not message.get(
                "more_body", False
            ):
                response_complete.set()

        await app(scope, receive, send)

    asyncio.run(run())
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if "body" in m)
    return start["status"], body


# --------------------------------------------------------------------------
# Route coverage
# --------------------------------------------------------------------------


def test_every_non_public_route_requires_token(client):
    calls = _protected_route_calls()
    # Guard against a vacuous pass if route discovery breaks.
    assert len(calls) >= 50
    failures = []
    for method, path in calls:
        response = client.request(method, path)
        if response.status_code != 401 or response.json() != CRED_ERROR:
            failures.append((method, path, response.status_code))
    assert failures == []


def test_every_api_route_carries_auth_dependency():
    missing = [
        route.path
        for route in app.routes
        if route.path.startswith("/api/")
        and get_current_user
        not in [d.call for d in getattr(route, "dependant").dependencies]
    ]
    assert missing == []


@pytest.mark.parametrize("path", sorted(PUBLIC_PATHS))
def test_public_routes_need_no_token(client, path):
    response = client.get(path)
    assert response.status_code == 200


# --------------------------------------------------------------------------
# API_DOCS_ENABLED
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", "false", "0", "no", "garbage"])
def test_docs_disabled_unless_flag_true(auth_env, make_token, value):
    if value is None:
        auth_env.delenv("API_DOCS_ENABLED", raising=False)
    else:
        auth_env.setenv("API_DOCS_ENABLED", value)
    docs_app = create_app()
    assert (docs_app.docs_url, docs_app.redoc_url, docs_app.openapi_url) == (
        None,
        None,
        None,
    )
    client = TestClient(docs_app, raise_server_exceptions=False)
    for path in sorted(DOCS_PATHS):
        _assert_rejected(client.get(path))
        authed = client.get(path, headers=_bearer(make_token()))
        assert authed.status_code == 404
        assert "openapi" not in authed.text
    assert "docs" not in client.get("/").json()


def test_default_app_does_not_serve_docs(client, make_token):
    for path in sorted(DOCS_PATHS):
        _assert_rejected(client.get(path))
        assert client.get(path, headers=_bearer(make_token())).status_code == 404


@pytest.mark.parametrize("value", ["true", "1", "TRUE", " yes "])
def test_docs_enabled_serves_public_docs(auth_env, value):
    auth_env.setenv("API_DOCS_ENABLED", value)
    client = TestClient(create_app(), raise_server_exceptions=False)
    for path in sorted(DOCS_PATHS):
        assert client.get(path).status_code == 200, path
    assert client.get("/openapi.json").json()["info"]["title"]
    assert client.get("/").json()["docs"] == "/docs"
    _assert_rejected(client.get("/api/v1/tasks/"))


@pytest.mark.parametrize(
    "path", ["/healthz", "/health/", "/docsx", "/api/v1/does-not-exist"]
)
def test_near_public_and_unknown_paths_are_denied(client, path):
    _assert_rejected(client.get(path))


def test_dot_segment_path_is_not_public(auth_env):
    status_code, body = _raw_asgi_get("/health/../api/v1/tasks/")
    assert status_code == 401
    assert json.loads(body) == CRED_ERROR


# --------------------------------------------------------------------------
# Valid tokens
# --------------------------------------------------------------------------


def test_valid_token_reaches_handler(client, make_token, db_calls):
    response = client.get("/api/v1/tasks/", headers=_bearer(make_token()))
    assert response.status_code not in (401, 403, 503)
    assert len(db_calls) == 1


def test_valid_token_sets_request_state_user(auth_env, make_token):
    seen = {}
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)

    @test_app.get("/whoami")
    async def whoami(user: dict = Depends(get_current_user)):
        seen.update(user)
        return user

    response = TestClient(test_app).get(
        "/whoami", headers=_bearer(make_token(role="manager"))
    )
    assert response.status_code == 200
    assert seen == {"id": "user-123", "email": "user@example.com", "role": "manager"}


def test_jwks_url_key_resolution(auth_env, make_token, rsa_keys, monkeypatch, db_calls):
    private_key, _ = rsa_keys
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "k1", "alg": "RS256", "use": "sig"})
    monkeypatch.delenv("AUTH_JWT_KEY")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://idp.test.example/jwks.json")
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk]})
    _reset_auth_caches()
    client = TestClient(app, raise_server_exceptions=False)

    ok = client.get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    assert ok.status_code not in (401, 403, 503)
    unknown_kid = make_token(headers={"kid": "other"})
    _assert_rejected(client.get("/api/v1/tasks/", headers=_bearer(unknown_kid)))


@pytest.fixture
def jwks(auth_env, rsa_keys, monkeypatch):
    """JWKS-configured auth with a counted, mocked fetch and an injected clock."""
    private_key, _ = rsa_keys
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "k1", "alg": "RS256", "use": "sig"})
    state = {
        "fetches": 0,
        "now": 1000.0,
        "error": None,
        "gate": None,
        "jwk": jwk,
        "data": None,
    }

    def _fetch(self):
        state["fetches"] += 1
        if state["gate"] is not None:
            assert state["gate"].wait(timeout=10)
        if state["error"] is not None:
            # Mimic older PyJWT, which clears the cache on a failed fetch.
            if self.jwk_set_cache is not None:
                self.jwk_set_cache.put(None)
            raise state["error"]
        data = state["data"] if state["data"] is not None else {"keys": [jwk]}
        # Older PyJWT (e.g. 2.12) fills the cache inside the real fetch_data.
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(data)
        return data

    monkeypatch.delenv("AUTH_JWT_KEY")
    monkeypatch.setenv("AUTH_JWKS_URL", JWKS_URL)
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _fetch)
    monkeypatch.setattr(auth_deps, "_monotonic", lambda: state["now"])
    _reset_auth_caches()
    return state


def test_jwks_client_uses_short_timeout_and_cache(jwks):
    client = auth_deps._jwks_client(JWKS_URL)
    assert client.timeout == 5
    assert client.jwk_set_cache is not None


def test_jwks_random_kids_cause_at_most_one_refetch(jwks, make_token, db_calls):
    client = TestClient(app, raise_server_exceptions=False)
    ok = client.get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    assert ok.status_code not in (401, 403, 503)
    assert jwks["fetches"] == 1  # initial JWK set load

    for i in range(50):
        token = make_token(headers={"kid": f"random-{i}"})
        _assert_rejected(client.get("/api/v1/tasks/", headers=_bearer(token)))
    assert jwks["fetches"] == 2  # one refetch for the whole window

    # A known kid still validates, from cache, inside the window.
    ok = client.get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    assert ok.status_code not in (401, 403, 503)
    assert jwks["fetches"] == 2


def test_jwks_refetch_allowed_again_after_window(jwks, make_token):
    client = TestClient(app, raise_server_exceptions=False)
    unknown = _bearer(make_token(headers={"kid": "nope"}))
    _assert_rejected(client.get("/api/v1/tasks/", headers=unknown))
    assert jwks["fetches"] == 2  # initial load + one refetch

    jwks["now"] += auth_deps.JWKS_UNKNOWN_KID_REFETCH_SECONDS - 1
    _assert_rejected(client.get("/api/v1/tasks/", headers=unknown))
    assert jwks["fetches"] == 2

    jwks["now"] += 1
    _assert_rejected(client.get("/api/v1/tasks/", headers=unknown))
    _assert_rejected(client.get("/api/v1/tasks/", headers=unknown))
    assert jwks["fetches"] == 3


def test_jwks_refetch_slot_is_thread_safe(jwks):
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(
            pool.map(lambda _: auth_deps._claim_unknown_kid_refetch(), range(200))
        )
    assert results.count(True) == 1


def test_jwks_fetch_error_is_503(jwks, make_token):
    jwks["error"] = jwt.PyJWKClientConnectionError("timed out to secret-host")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    assert response.status_code == 503
    assert "secret-host" not in response.text


def test_jwks_token_alg_must_match_alg_declared_by_jwk(jwks, make_token):
    # The key is usable for RS256, but the IdP declared it for PS256 only.
    jwks["jwk"]["alg"] = "PS256"
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    _assert_rejected(response)


def test_jwks_key_without_declared_alg_still_validates(jwks, make_token, db_calls):
    del jwks["jwk"]["alg"]
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    assert response.status_code not in (401, 403, 503)


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(lambda s: s.update(error=ValueError("not json")), id="bad-json"),
        pytest.param(lambda s: s.update(data={"keys": []}), id="empty-key-set"),
        pytest.param(lambda s: s.update(data={"nokeys": 1}), id="no-keys-field"),
    ],
)
def test_jwks_malformed_response_is_503(jwks, make_token, setup):
    setup(jwks)
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    assert response.status_code == 503


def test_jwks_refetch_error_for_unknown_kid_is_503(jwks, make_token, db_calls):
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"})))
    jwks["error"] = jwt.PyJWKClientConnectionError("down")
    response = client.get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "new"}))
    )
    assert response.status_code == 503


def test_jwks_fetch_failure_backs_off_then_retries(jwks, make_token):
    jwks["error"] = jwt.PyJWKClientConnectionError("down")
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/api/v1/tasks/", headers=_bearer("garbage")).status_code == 401
    token = _bearer(make_token(headers={"kid": "k1"}))
    assert client.get("/api/v1/tasks/", headers=token).status_code == 503
    assert jwks["fetches"] == 1

    for i in range(50):
        kid_token = _bearer(make_token(headers={"kid": f"k-{i}"}))
        assert client.get("/api/v1/tasks/", headers=kid_token).status_code == 503
    assert jwks["fetches"] == 1

    jwks["now"] += auth_deps.JWKS_FETCH_FAILURE_BACKOFF_SECONDS
    assert client.get("/api/v1/tasks/", headers=token).status_code == 503
    assert jwks["fetches"] == 2


def test_jwks_concurrent_requests_single_flight(jwks, make_token):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    gate = threading.Event()
    jwks["gate"] = gate
    settings = auth_deps.get_auth_settings()
    token = make_token(headers={"kid": "k1"})
    leader = threading.Thread(target=auth_deps._resolve_key, args=(settings, token))
    leader.start()
    for _ in range(100):
        if jwks["fetches"]:
            break
        time.sleep(0.01)
    assert jwks["fetches"] == 1

    def _attempt(_):
        try:
            auth_deps._resolve_key(settings, token)
        except auth_deps.AuthUnavailableError:
            return "503"
        return "ok"

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(_attempt, range(50)))
    gate.set()
    leader.join(timeout=10)
    assert results == ["503"] * 50
    assert jwks["fetches"] == 1
    # After the in-flight fetch succeeded, requests are served from cache.
    assert auth_deps._resolve_key(settings, token) is not None
    assert jwks["fetches"] == 1


def test_jwks_failed_refetch_keeps_valid_cache(jwks, make_token, db_calls):
    client = TestClient(app, raise_server_exceptions=False)
    known = _bearer(make_token(headers={"kid": "k1"}))
    assert client.get("/api/v1/tasks/", headers=known).status_code not in (
        401,
        403,
        503,
    )
    jwks["error"] = jwt.PyJWKClientConnectionError("down")
    unknown = _bearer(make_token(headers={"kid": "rotated"}))
    assert client.get("/api/v1/tasks/", headers=unknown).status_code == 503
    assert jwks["fetches"] == 2
    for _ in range(5):
        ok = client.get("/api/v1/tasks/", headers=known)
        assert ok.status_code not in (401, 403, 503)
    assert jwks["fetches"] == 2


def test_jwks_unreachable_fails_closed(auth_env, make_token, monkeypatch):
    def _boom(self):
        raise jwt.PyJWKClientConnectionError("connection refused to secret-host")

    monkeypatch.delenv("AUTH_JWT_KEY")
    monkeypatch.setenv("AUTH_JWKS_URL", "https://idp.test.example/jwks.json")
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _boom)
    _reset_auth_caches()
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
    )
    assert response.status_code == 503
    assert "secret-host" not in response.text


def test_hs256_shared_secret_config(auth_env, db_calls):
    secret = "s" * 48
    auth_env.setenv("AUTH_JWT_ALGORITHMS", "HS256")
    auth_env.setenv("AUTH_JWT_KEY", secret)
    _reset_auth_caches()
    token = jwt.encode(_claims(), secret, algorithm="HS256")
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/tasks/", headers=_bearer(token)
    )
    assert response.status_code not in (401, 403, 503)


# --------------------------------------------------------------------------
# Invalid tokens: all 401 with the generic body
# --------------------------------------------------------------------------


def _bad_token_cases(make_token, rsa_keys) -> Dict[str, Dict[str, str]]:
    _, public_pem = rsa_keys
    now = int(time.time())
    hs_input = _unsigned_token({"alg": "HS256", "typ": "JWT"}, _claims())
    hs_sig = hmac.new(public_pem.encode(), hs_input.encode(), hashlib.sha256)
    key_confusion = hs_input + "." + _b64url(hs_sig.digest())
    alg_none = _unsigned_token({"alg": "none", "typ": "JWT"}, _claims()) + "."
    valid = make_token()
    return {
        "expired": _bearer(make_token(iat=now - 3600, exp=now - 120)),
        "wrong_issuer": _bearer(make_token(iss="https://evil.example/")),
        "wrong_audience": _bearer(make_token(aud="someone-else")),
        "missing_sub": _bearer(make_token(sub=_MISSING)),
        "empty_sub": _bearer(make_token(sub="")),
        "missing_exp": _bearer(make_token(exp=_MISSING)),
        "missing_iat": _bearer(make_token(iat=_MISSING)),
        "missing_iss": _bearer(make_token(iss=_MISSING)),
        "missing_aud": _bearer(make_token(aud=_MISSING)),
        "alg_none": _bearer(alg_none),
        "hs256_key_confusion": _bearer(key_confusion),
        "tampered_payload": _bearer(
            valid.split(".")[0]
            + "."
            + _b64url(json.dumps(_claims(role="admin")).encode())
            + "."
            + valid.split(".")[2]
        ),
        "garbage": _bearer("not-a-jwt"),
        "garbage_dots": _bearer("a.b.c"),
        "basic_scheme": {"Authorization": "Basic dXNlcjpwYXNz"},
        "token_scheme": {"Authorization": f"Token {valid}"},
        "bare_token": {"Authorization": valid},
        "empty_bearer": {"Authorization": "Bearer "},
        "no_header": {},
    }


CASE_NAMES = [
    "expired",
    "wrong_issuer",
    "wrong_audience",
    "missing_sub",
    "empty_sub",
    "missing_exp",
    "missing_iat",
    "missing_iss",
    "missing_aud",
    "alg_none",
    "hs256_key_confusion",
    "tampered_payload",
    "garbage",
    "garbage_dots",
    "basic_scheme",
    "token_scheme",
    "bare_token",
    "empty_bearer",
    "no_header",
]


@pytest.mark.parametrize("case", CASE_NAMES)
def test_invalid_credentials_rejected(client, make_token, rsa_keys, db_calls, case):
    headers = _bad_token_cases(make_token, rsa_keys)[case]
    response = client.get("/api/v1/tasks/", headers=headers)
    _assert_rejected(response)
    # Generic body only: no exception text leaks.
    for leak in ("expired", "issuer", "audience", "signature", "algorithm", "Error"):
        assert leak not in response.text
    assert db_calls == []


# --------------------------------------------------------------------------
# Missing / unsafe configuration: 503, never 200
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env_change",
    [
        {"AUTH_JWT_ISSUER": None},
        {"AUTH_JWT_AUDIENCE": None},
        {"AUTH_JWT_KEY": None},
        {"AUTH_JWT_ALGORITHMS": "none"},
        {"AUTH_JWT_ALGORITHMS": "RS256,HS256"},
        {"AUTH_JWT_ALGORITHMS": "XS999"},
        {"AUTH_JWT_ALGORITHMS": "HS256", "AUTH_JWT_KEY": "too-short"},
        {"AUTH_JWT_KEY": "not a pem key"},
        {"AUTH_JWKS_URL": "https://idp.test.example/jwks.json"},
        {"AUTH_JWKS_URL": "http://idp.test.example/jwks.json", "AUTH_JWT_KEY": None},
    ],
)
def test_missing_or_unsafe_config_fails_closed(
    auth_env, make_token, db_calls, caplog, env_change
):
    for name, value in env_change.items():
        if value is None:
            auth_env.delenv(name, raising=False)
        else:
            auth_env.setenv(name, value)
    _reset_auth_caches()
    client = TestClient(app, raise_server_exceptions=False)

    for headers in ({}, _bearer(make_token())):
        response = client.get("/api/v1/tasks/", headers=headers)
        assert response.status_code == 503
        assert response.json() == NOT_CONFIGURED
    assert db_calls == []
    assert any(
        r.levelname == "ERROR" and "not configured" in r.getMessage()
        for r in caplog.records
    )
    # Public routes stay up even when auth is misconfigured.
    assert client.get("/health").status_code == 200


# --------------------------------------------------------------------------
# Middleware ordering: CORS -> Auth -> Governance
# --------------------------------------------------------------------------


def test_middleware_stack_order():
    names = [m.cls.__name__ for m in app.user_middleware]  # outermost first
    assert names.index("CORSMiddleware") < names.index("AuthMiddleware")
    assert names.index("AuthMiddleware") < names.index("GovernanceMiddleware")


def test_401_carries_cors_headers(client):
    response = client.get("/api/v1/tasks/", headers={"Origin": ALLOWED_ORIGIN})
    _assert_rejected(response)
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_cors_preflight_passes_without_token(client):
    response = client.options(
        "/api/v1/tasks/",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


def test_plain_options_without_preflight_headers_is_denied(client):
    _assert_rejected(client.options("/api/v1/tasks/"))


def test_unauthenticated_request_never_reaches_governance(
    client, make_token, monkeypatch
):
    governance = MagicMock()
    governance.validate_operation.return_value = {
        "action": "BLOCK",
        "violations": [],
        "decision_id": "d-1",
    }
    monkeypatch.setattr(governance_interceptor, "get_governance", lambda: governance)
    path = "/api/v1/recommendations/generate"

    _assert_rejected(client.post(path, json={"q": 1}))
    _assert_rejected(client.post(path, headers=_bearer("garbage")))
    governance.validate_operation.assert_not_called()

    # Positive control: the patch target is live once authenticated.
    response = client.post(path, json={"q": 1}, headers=_bearer(make_token()))
    assert response.status_code == 403
    governance.validate_operation.assert_called_once()


# --------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------


@pytest.fixture
def role_client(auth_env) -> TestClient:
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)

    @test_app.get("/manager-only")
    async def manager_only(user: dict = Depends(require_role("manager"))):
        return {"role": user["role"]}

    return TestClient(test_app)


@pytest.mark.parametrize(
    "role, expected",
    [
        ("viewer", 403),
        ("user", 403),
        ("manager", 200),
        ("admin", 200),
        ("superuser", 403),  # unknown -> lowest privilege
        (_MISSING, 403),  # missing -> viewer, not user
        (["admin"], 403),  # non-string -> lowest privilege
    ],
)
def test_require_role(role_client, make_token, role, expected):
    response = role_client.get("/manager-only", headers=_bearer(make_token(role=role)))
    assert response.status_code == expected


def test_missing_role_maps_to_viewer(auth_env, make_token):
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)

    @test_app.get("/me")
    async def me(user: dict = Depends(get_current_user)):
        return user

    response = TestClient(test_app).get(
        "/me", headers=_bearer(make_token(role=_MISSING))
    )
    assert response.json()["role"] == "viewer"


def test_custom_role_claim(auth_env, make_token):
    auth_env.setenv("AUTH_ROLE_CLAIM", "acgs_role")
    _reset_auth_caches()
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)

    @test_app.get("/me")
    async def me(user: dict = Depends(get_current_user)):
        return user

    token = make_token(role="admin", acgs_role="manager")
    assert TestClient(test_app).get("/me", headers=_bearer(token)).json()["role"] == (
        "manager"
    )


def test_get_current_user_without_middleware_is_401():
    test_app = FastAPI()

    @test_app.get("/me")
    async def me(user: dict = Depends(get_current_user)):
        return user

    response = TestClient(test_app).get("/me")
    assert response.status_code == 401
    assert response.json() == CRED_ERROR


def test_jwks_unusable_key_set_does_not_refetch_every_request(jwks, make_token):
    jwks["data"] = {"keys": []}
    client = TestClient(app, raise_server_exceptions=False)
    for _ in range(20):
        response = client.get(
            "/api/v1/tasks/", headers=_bearer(make_token(headers={"kid": "k1"}))
        )
        assert response.status_code == 503
    assert jwks["fetches"] <= 1
