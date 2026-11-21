"""
Authentication and Authorization Module

This API only VERIFIES bearer JWTs issued by an external identity provider.
It never mints tokens and never falls back to a default key: if the
configuration is missing or unsafe, protected requests fail closed (503).

Configuration (environment, read via the cached ``get_auth_settings()``):
    AUTH_JWT_ISSUER      required, expected ``iss``
    AUTH_JWT_AUDIENCE    required, expected ``aud``
    AUTH_JWT_ALGORITHMS  comma list, default ``RS256``
    AUTH_JWKS_URL        JWKS endpoint of the IdP (preferred), or
    AUTH_JWT_KEY         PEM public key (RS*/PS*/ES*/EdDSA) or shared secret (HS*)
    AUTH_ROLE_CLAIM      claim holding the role, default ``role``
"""

import logging
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

CREDENTIALS_ERROR_DETAIL = "Could not validate credentials"
NOT_CONFIGURED_DETAIL = "Authentication not configured"
UNAVAILABLE_DETAIL = "Authentication service unavailable"

REQUIRED_CLAIMS = ["exp", "iat", "sub", "iss", "aud"]
LEEWAY_SECONDS = 30
MIN_HMAC_SECRET_BYTES = 32

HMAC_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})
ASYMMETRIC_ALGORITHMS = frozenset(
    {
        "RS256",
        "RS384",
        "RS512",
        "PS256",
        "PS384",
        "PS512",
        "ES256",
        "ES384",
        "ES512",
        "EdDSA",
    }
)

# JWKS fetching. An unknown ``kid`` may force a JWKS refetch at most once per
# JWKS_UNKNOWN_KID_REFETCH_SECONDS, process-wide; inside that window unknown
# kids are rejected without any outbound request (unauthenticated DoS guard).
JWKS_FETCH_TIMEOUT_SECONDS = 5
JWKS_CACHE_LIFESPAN_SECONDS = 300
JWKS_UNKNOWN_KID_REFETCH_SECONDS = 60
_monotonic = time.monotonic  # injectable clock for tests
_unknown_kid_refetch_lock = threading.Lock()
_last_unknown_kid_refetch: Optional[float] = None
# After a failed JWKS fetch, no fetch is attempted for this long (503 instead),
# and only one fetch may be in flight at a time (others get 503, not a fetch).
JWKS_FETCH_FAILURE_BACKOFF_SECONDS = 30
_jwks_fetch_lock = threading.Lock()  # single-flight; never waited on
_jwks_state_lock = threading.Lock()
_jwks_fetch_failed_at: Optional[float] = None

# Role hierarchy: admin > manager > user > viewer
ROLE_HIERARCHY = {"admin": 3, "manager": 2, "user": 1, "viewer": 0}
LOWEST_ROLE = "viewer"


class AuthConfigError(Exception):
    """Authentication configuration is missing or unsafe."""


class AuthUnavailableError(Exception):
    """Key material could not be retrieved (e.g. JWKS endpoint unreachable)."""


class InvalidCredentialsError(Exception):
    """The presented token is not acceptable. Never surfaced to clients."""


@dataclass(frozen=True)
class AuthSettings:
    algorithms: Tuple[str, ...]
    issuer: str
    audience: str
    role_claim: str
    jwks_url: Optional[str]
    key: Any  # loaded public key object or HMAC secret; None when using JWKS


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    """Load and validate auth config from the environment.

    Raises AuthConfigError on any missing or unsafe setting. Successful results
    are cached; call ``get_auth_settings.cache_clear()`` after changing env.
    """
    issuer = _env("AUTH_JWT_ISSUER")
    audience = _env("AUTH_JWT_AUDIENCE")
    if not issuer or not audience:
        raise AuthConfigError("AUTH_JWT_ISSUER and AUTH_JWT_AUDIENCE are required")

    raw_algs = _env("AUTH_JWT_ALGORITHMS") or "RS256"
    algorithms = tuple(a.strip() for a in raw_algs.split(",") if a.strip())
    if not algorithms:
        raise AuthConfigError("AUTH_JWT_ALGORITHMS is empty")
    for alg in algorithms:
        if alg.lower() == "none":
            raise AuthConfigError("Algorithm 'none' is not allowed")
        if alg not in HMAC_ALGORITHMS and alg not in ASYMMETRIC_ALGORITHMS:
            raise AuthConfigError(f"Unsupported algorithm: {alg}")
    uses_hmac = any(a in HMAC_ALGORITHMS for a in algorithms)
    uses_asym = any(a in ASYMMETRIC_ALGORITHMS for a in algorithms)
    if uses_hmac and uses_asym:
        raise AuthConfigError(
            "Mixing HS* with asymmetric algorithms is refused (key confusion)"
        )

    jwks_url = _env("AUTH_JWKS_URL") or None
    raw_key = os.environ.get("AUTH_JWT_KEY", "")
    if jwks_url and raw_key.strip():
        raise AuthConfigError("Set only one of AUTH_JWKS_URL or AUTH_JWT_KEY")
    if not jwks_url and not raw_key.strip():
        raise AuthConfigError("One of AUTH_JWKS_URL or AUTH_JWT_KEY is required")

    key: Any = None
    if jwks_url:
        if uses_hmac:
            raise AuthConfigError("AUTH_JWKS_URL requires asymmetric algorithms")
        if not jwks_url.startswith("https://"):
            raise AuthConfigError("AUTH_JWKS_URL must use https")
    elif uses_hmac:
        if len(raw_key.encode()) < MIN_HMAC_SECRET_BYTES:
            raise AuthConfigError(
                f"HS* secret must be at least {MIN_HMAC_SECRET_BYTES} bytes"
            )
        if "-----BEGIN" in raw_key:
            raise AuthConfigError("HS* secret must not be a PEM key")
        key = raw_key
    else:
        try:
            key = load_pem_public_key(raw_key.strip().encode())
        except Exception:
            raise AuthConfigError("AUTH_JWT_KEY is not a valid PEM public key")

    return AuthSettings(
        algorithms=algorithms,
        issuer=issuer,
        audience=audience,
        role_claim=_env("AUTH_ROLE_CLAIM") or "role",
        jwks_url=jwks_url,
        key=key,
    )


def _jwks_in_backoff() -> bool:
    with _jwks_state_lock:
        failed_at = _jwks_fetch_failed_at
    return (
        failed_at is not None
        and _monotonic() - failed_at < JWKS_FETCH_FAILURE_BACKOFF_SECONDS
    )


def _set_jwks_fetch_failed_at(value: Optional[float]) -> None:
    global _jwks_fetch_failed_at
    with _jwks_state_lock:
        _jwks_fetch_failed_at = value


class _GuardedJWKClient(jwt.PyJWKClient):
    """PyJWKClient whose every network fetch is single-flight with backoff.

    A failed fetch never clears a still-valid cached key set, so known kids
    keep validating during an IdP outage until the cache expires.
    """

    def fetch_data(self) -> Any:
        if _jwks_in_backoff():
            raise AuthUnavailableError("JWKS fetch in failure backoff")
        if not _jwks_fetch_lock.acquire(blocking=False):
            raise AuthUnavailableError("JWKS fetch already in progress")
        cache = self.jwk_set_cache
        cached = cache.jwk_set_with_timestamp if cache is not None else None
        try:
            if _jwks_in_backoff():
                raise AuthUnavailableError("JWKS fetch in failure backoff")
            try:
                data = super().fetch_data()
            except Exception:
                _set_jwks_fetch_failed_at(_monotonic())
                if cache is not None:
                    # Older PyJWT clears the cache on a failed fetch.
                    cache.jwk_set_with_timestamp = cached
                raise
            _set_jwks_fetch_failed_at(None)
            return data
        finally:
            _jwks_fetch_lock.release()


@lru_cache(maxsize=4)
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return _GuardedJWKClient(
        url,
        cache_jwk_set=True,
        lifespan=JWKS_CACHE_LIFESPAN_SECONDS,
        timeout=JWKS_FETCH_TIMEOUT_SECONDS,
    )


def _claim_unknown_kid_refetch() -> bool:
    """Atomically take the process-wide unknown-kid refetch slot, if free."""
    global _last_unknown_kid_refetch
    now = _monotonic()
    with _unknown_kid_refetch_lock:
        last = _last_unknown_kid_refetch
        if last is not None and now - last < JWKS_UNKNOWN_KID_REFETCH_SECONDS:
            return False
        _last_unknown_kid_refetch = now
        return True


def _resolve_key(settings: AuthSettings, token: str) -> Any:
    if settings.jwks_url is None:
        return settings.key
    client = _jwks_client(settings.jwks_url)
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        # Served from the cached JWK set; fetches only when empty or expired.
        signing_key = client.match_kid(client.get_signing_keys(), kid)
        if signing_key is None:
            if not _claim_unknown_kid_refetch():
                raise InvalidCredentialsError()
            refreshed = client.get_signing_keys(refresh=True)
            signing_key = client.match_kid(refreshed, kid)
        if signing_key is None:
            raise InvalidCredentialsError()
        # A JWK that declares "alg" may only verify tokens using that algorithm.
        # PyJWK.algorithm_name is inferred when "alg" is absent, so read the raw
        # JWK; a PyJWT without _jwk_data fails closed here (tests pin this).
        declared_alg = signing_key._jwk_data.get("alg")
        if declared_alg is not None and header.get("alg") != declared_alg:
            raise InvalidCredentialsError()
        return signing_key.key
    except jwt.PyJWKClientConnectionError:
        raise AuthUnavailableError("JWKS endpoint unreachable")
    except (jwt.PyJWKClientError, jwt.PyJWKSetError, ValueError):
        # The endpoint answered, but with no usable signing keys or invalid JSON:
        # an IdP-side problem, not a bad token.
        raise AuthUnavailableError("JWKS response unusable")
    except jwt.PyJWTError:
        raise InvalidCredentialsError()


def map_role(value: Any) -> str:
    """Map a role claim to a known role. Missing or unknown -> lowest privilege."""
    if isinstance(value, str) and value in ROLE_HIERARCHY:
        return value
    return LOWEST_ROLE


async def verify_token(token: str, settings: AuthSettings) -> Dict[str, Any]:
    """Verify a bearer token and return the user dict.

    Raises InvalidCredentialsError for any token problem and
    AuthUnavailableError if key material cannot be fetched.
    """
    key = await run_in_threadpool(_resolve_key, settings, token)
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=list(settings.algorithms),
            audience=settings.audience,
            issuer=settings.issuer,
            options={"require": REQUIRED_CLAIMS},
            leeway=LEEWAY_SECONDS,
        )
    except Exception:
        # Any decode failure, including unexpected ones, is a rejection.
        raise InvalidCredentialsError()

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise InvalidCredentialsError()

    return {
        "id": sub,
        "email": payload.get("email"),
        "role": map_role(payload.get(settings.role_claim)),
    }


# auto_error=False: the AuthMiddleware does the real enforcement; this only
# advertises the bearer scheme in OpenAPI so /docs offers "Authorize".
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    _credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """Return the user authenticated by AuthMiddleware (defence in depth).

    Raises 401 if the middleware did not set ``request.state.user``.
    """
    user = getattr(request.state, "user", None)
    if not isinstance(user, dict) or not user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=CREDENTIALS_ERROR_DETAIL,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(required_role: str):
    """
    Dependency factory to require a minimum role.

    Usage:
        @app.get("/admin")
        async def admin_route(user: dict = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}
    """
    if required_role not in ROLE_HIERARCHY:
        raise ValueError(f"Unknown role: {required_role}")

    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = map_role(user.get("role"))
        if ROLE_HIERARCHY[user_role] < ROLE_HIERARCHY[required_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return role_checker
