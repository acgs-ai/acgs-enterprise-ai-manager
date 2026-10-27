"""
Role-based authorization middleware.

Applies backend.auth.policy to every /api/v1 request. Must sit inside
AuthMiddleware (it needs ``request.state.user``) and outside
GovernanceMiddleware, so a request the caller may not make never reaches
governance (no approval requests, no audit records, no decision details).
Paths outside /api/v1 pass through unchanged.
"""

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.auth.policy import authorization_error

API_PREFIX = "/api/v1"


def _is_api_path(path: str) -> bool:
    return path == API_PREFIX or path.startswith(API_PREFIX + "/")


class RBACMiddleware(BaseHTTPMiddleware):
    """Refuse /api/v1 requests the policy does not allow, before governance."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _is_api_path(request.scope.get("path", "")):
            return await call_next(request)
        user = getattr(request.state, "user", None)
        detail = authorization_error(request.app.router.routes, request.scope, user)
        if detail is not None:
            return JSONResponse(status_code=403, content={"detail": detail})
        return await call_next(request)
