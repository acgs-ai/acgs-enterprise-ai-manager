"""
Authentication Middleware

Default-deny bearer-token enforcement for every path except an exact public
allowlist. Must sit inside CORSMiddleware (so 401s carry CORS headers) and
outside GovernanceMiddleware (so unauthenticated requests never reach it).
"""

import logging
import os
from typing import Callable, FrozenSet, Iterable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.auth.dependencies import (
    CREDENTIALS_ERROR_DETAIL,
    NOT_CONFIGURED_DETAIL,
    UNAVAILABLE_DETAIL,
    AuthConfigError,
    AuthUnavailableError,
    InvalidCredentialsError,
    get_auth_settings,
    verify_token,
)

logger = logging.getLogger(__name__)

# Exact matches only. No prefixes: "/healthz", "/health/" and
# "/health/../api" are NOT public.
PUBLIC_PATHS = frozenset({"/health", "/"})

# Interactive docs and the OpenAPI schema. Public only when API_DOCS_ENABLED
# is true; otherwise FastAPI does not serve them and they need a token.
DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"})

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def api_docs_enabled() -> bool:
    """Read API_DOCS_ENABLED. Anything but an explicit true value is false."""
    return os.environ.get("API_DOCS_ENABLED", "").strip().lower() in _TRUE_VALUES


def public_paths(docs_enabled: bool) -> FrozenSet[str]:
    return PUBLIC_PATHS | DOCS_PATHS if docs_enabled else PUBLIC_PATHS


def _unauthorized() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": CREDENTIALS_ERROR_DETAIL},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _is_cors_preflight(request: Request) -> bool:
    return (
        request.method == "OPTIONS"
        and "origin" in request.headers
        and "access-control-request-method" in request.headers
    )


class AuthMiddleware(BaseHTTPMiddleware):
    """Verify the bearer JWT and set ``request.state.user``.

    ``public_paths`` defaults to PUBLIC_PATHS (docs not public).
    """

    def __init__(self, app, public_paths: Optional[Iterable[str]] = None) -> None:
        super().__init__(app)
        self.public_paths = frozenset(
            PUBLIC_PATHS if public_paths is None else public_paths
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.scope.get("path", "")
        if path in self.public_paths or _is_cors_preflight(request):
            return await call_next(request)

        try:
            settings = get_auth_settings()
        except AuthConfigError as exc:
            logger.error("Authentication not configured: %s", exc)
            return JSONResponse(
                status_code=503, content={"detail": NOT_CONFIGURED_DETAIL}
            )

        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token or " " in token:
            return _unauthorized()

        try:
            user = await verify_token(token, settings)
        except InvalidCredentialsError:
            logger.info("Rejected bearer token for %s %s", request.method, path)
            return _unauthorized()
        except AuthUnavailableError as exc:
            logger.error("Authentication key material unavailable: %s", exc)
            return JSONResponse(status_code=503, content={"detail": UNAVAILABLE_DETAIL})
        except Exception:
            logger.exception("Unexpected error during token verification")
            return _unauthorized()

        request.state.user = user
        return await call_next(request)
