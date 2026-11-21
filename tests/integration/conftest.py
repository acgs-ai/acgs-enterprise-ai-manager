"""Shared auth fixtures for the API integration tests."""

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import backend.middleware.governance_interceptor as governance_interceptor
from backend.database import get_db
from backend.main import app
from tests.integration._auth_helpers import (
    AUDIENCE,
    ISSUER,
    _claims,
    _reset_auth_caches,
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


@pytest.fixture
def allow_governance(monkeypatch):
    """Stub governance to ALLOW. Opt in per file via ``usefixtures``."""
    governance = MagicMock()
    governance.validate_operation.return_value = {
        "action": "ALLOW",
        "violations": [],
        "decision_id": "d-test",
    }
    monkeypatch.setattr(governance_interceptor, "get_governance", lambda: governance)
    return governance
