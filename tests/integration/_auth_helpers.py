"""Shared constants and helpers for the API auth integration tests."""

import re
import time
from typing import Any, Dict

import backend.auth.dependencies as auth_deps

ISSUER = "https://idp.test.example/"
AUDIENCE = "acgs-enterprise-manager"
CRED_ERROR = {"detail": "Could not validate credentials"}
_MISSING = object()


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


def _bearer(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _concrete_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000001", path)


def _reset_auth_caches() -> None:
    auth_deps.get_auth_settings.cache_clear()
    auth_deps._jwks_client.cache_clear()
    auth_deps._last_unknown_kid_refetch = None
    auth_deps._jwks_fetch_failed_at = None
