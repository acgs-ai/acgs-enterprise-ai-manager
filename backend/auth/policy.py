"""
Route authorization policy.

ROUTE_POLICY maps (HTTP method, route path template) to the minimum role
allowed to call it. Templates are exactly ``APIRoute.path`` (prefix included).
Every entry is explicit: there are no wildcards, prefixes or defaults.

New routes MUST be added to ROUTE_POLICY. A route with no entry is refused
with 403 for every role, including admin (fail closed), and CI enforces full
coverage (tests/integration/test_api_rbac.py).

The policy is enforced twice through one decision function,
``authorization_error``: by RBACMiddleware (between AuthMiddleware and
GovernanceMiddleware, so a denied request never reaches governance) and by the
``enforce_route_policy`` route dependency (defence in depth). There is no HEAD
mapping: APIRoute does not accept HEAD, so HEAD under /api/v1 matches no route
and is refused.
"""

import logging
from typing import Any, Dict, Iterable, Optional, Tuple

from fastapi import Depends, HTTPException, Request, status
from starlette.routing import BaseRoute, Match

from backend.auth.dependencies import ROLE_HIERARCHY, get_current_user, map_role

logger = logging.getLogger(__name__)

FORBIDDEN_DETAIL = "Forbidden"
INSUFFICIENT_PERMISSIONS_DETAIL = "Insufficient permissions"

ROUTE_POLICY: Dict[Tuple[str, str], str] = {
    # Tasks
    ("GET", "/api/v1/tasks/"): "viewer",
    ("POST", "/api/v1/tasks/"): "user",
    ("GET", "/api/v1/tasks/{task_id}"): "viewer",
    ("PUT", "/api/v1/tasks/{task_id}"): "user",
    ("DELETE", "/api/v1/tasks/{task_id}"): "manager",
    ("POST", "/api/v1/tasks/{task_id}/assets"): "user",
    ("POST", "/api/v1/tasks/{task_id}/infrastructure"): "user",
    ("GET", "/api/v1/tasks/project/{project_id}"): "viewer",
    ("GET", "/api/v1/tasks/user/{user_id}"): "viewer",
    # Recommendations
    ("POST", "/api/v1/recommendations/generate"): "user",
    ("POST", "/api/v1/recommendations/batch"): "user",
    ("GET", "/api/v1/recommendations/top/{domain}"): "viewer",
    ("GET", "/api/v1/recommendations/domains"): "viewer",
    ("GET", "/api/v1/recommendations/stats"): "viewer",
    ("GET", "/api/v1/recommendations/health"): "viewer",
    # Search
    ("GET", "/api/v1/search/"): "viewer",
    ("GET", "/api/v1/search/domain/{domain}"): "viewer",
    ("GET", "/api/v1/search/tags"): "viewer",
    ("GET", "/api/v1/search/suggest"): "viewer",
    ("GET", "/api/v1/search/tags/popular"): "viewer",
    ("GET", "/api/v1/search/stats"): "viewer",
    ("POST", "/api/v1/search/reindex"): "admin",
    ("GET", "/api/v1/search/domains"): "viewer",
    # Projects
    ("GET", "/api/v1/projects/"): "viewer",
    ("POST", "/api/v1/projects/"): "user",
    ("GET", "/api/v1/projects/{project_id}"): "viewer",
    ("PUT", "/api/v1/projects/{project_id}"): "user",
    ("DELETE", "/api/v1/projects/{project_id}"): "manager",
    # IT assets
    ("GET", "/api/v1/assets/"): "viewer",
    ("POST", "/api/v1/assets/"): "user",
    ("GET", "/api/v1/assets/{asset_id}"): "viewer",
    ("PUT", "/api/v1/assets/{asset_id}"): "user",
    ("DELETE", "/api/v1/assets/{asset_id}"): "manager",
    ("GET", "/api/v1/assets/project/{project_id}"): "viewer",
    ("GET", "/api/v1/assets/owner/{owner_id}"): "viewer",
    ("GET", "/api/v1/assets/lifecycle/{stage}"): "viewer",
    # Infrastructure
    ("GET", "/api/v1/infrastructure/"): "viewer",
    ("POST", "/api/v1/infrastructure/"): "user",
    ("GET", "/api/v1/infrastructure/{infra_id}"): "viewer",
    ("PUT", "/api/v1/infrastructure/{infra_id}"): "user",
    ("DELETE", "/api/v1/infrastructure/{infra_id}"): "manager",
    # Documents
    ("GET", "/api/v1/documents/"): "viewer",
    ("POST", "/api/v1/documents/"): "user",
    ("GET", "/api/v1/documents/{doc_id}"): "viewer",
    ("PUT", "/api/v1/documents/{doc_id}"): "user",
    ("DELETE", "/api/v1/documents/{doc_id}"): "manager",
    # Financial
    ("GET", "/api/v1/financial/"): "viewer",
    ("POST", "/api/v1/financial/"): "manager",
    ("GET", "/api/v1/financial/{record_id}"): "viewer",
    ("PUT", "/api/v1/financial/{record_id}"): "manager",
    ("DELETE", "/api/v1/financial/{record_id}"): "manager",
    ("POST", "/api/v1/financial/{record_id}/approve"): "manager",
    ("POST", "/api/v1/financial/{record_id}/reject"): "manager",
    # Reports
    ("GET", "/api/v1/reports/reports/dashboard"): "viewer",
    ("GET", "/api/v1/reports/reports/executive-summary"): "viewer",
    ("GET", "/api/v1/reports/reports/tasks/detailed"): "viewer",
    ("GET", "/api/v1/reports/reports/assets/detailed"): "viewer",
    ("GET", "/api/v1/reports/reports/projects/detailed"): "viewer",
    ("GET", "/api/v1/reports/reports/financial/detailed"): "viewer",
    ("GET", "/api/v1/reports/reports/documents/detailed"): "viewer",
    ("GET", "/api/v1/reports/reports/tasks/completion-trend"): "viewer",
    ("GET", "/api/v1/reports/reports/assets/utilization"): "viewer",
    ("GET", "/api/v1/reports/reports/projects/health"): "viewer",
    ("GET", "/api/v1/reports/reports/financial/burn-rate"): "viewer",
    ("GET", "/api/v1/reports/reports/financial/cash-flow-trend"): "viewer",
    ("GET", "/api/v1/reports/reports/documents/activity"): "viewer",
}


def resolve_route_template(
    routes: Iterable[BaseRoute], scope: Dict[str, Any]
) -> Optional[str]:
    """Return the path template of the route Starlette would dispatch to.

    Like Starlette's router, the first route with a FULL match wins. A PARTIAL
    match (path matches, method does not) or no match returns None.
    """
    for route in routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return getattr(route, "path", None)
    return None


def authorization_error(
    routes: Iterable[BaseRoute], scope: Dict[str, Any], user: Any
) -> Optional[str]:
    """Decide one request. Returns None if allowed, else the 403 detail.

    Shared by RBACMiddleware and enforce_route_policy so the two cannot drift.
    Every denial is logged with the user id, method and template (or the raw
    path when nothing matched); the token is never logged.
    """
    method = str(scope.get("method", "")).upper()
    user_id = user.get("id") if isinstance(user, dict) else None
    template = resolve_route_template(routes, scope)
    if template is None:
        logger.warning(
            "Authorization denied (no matching route): user=%r method=%s path=%r",
            user_id,
            method,
            scope.get("path"),
        )
        return FORBIDDEN_DETAIL

    required = ROUTE_POLICY.get((method, template))
    if required not in ROLE_HIERARCHY:
        logger.error(
            "Authorization denied (no policy entry): user=%r method=%s template=%s",
            user_id,
            method,
            template,
        )
        return FORBIDDEN_DETAIL

    if user_id is None:
        logger.warning(
            "Authorization denied (no authenticated user): method=%s template=%s",
            method,
            template,
        )
        return FORBIDDEN_DETAIL

    if ROLE_HIERARCHY[map_role(user.get("role"))] < ROLE_HIERARCHY[required]:
        logger.warning(
            "Authorization denied (role too low): user=%r method=%s template=%s",
            user_id,
            method,
            template,
        )
        return INSUFFICIENT_PERMISSIONS_DETAIL
    return None


async def enforce_route_policy(
    request: Request, user: dict = Depends(get_current_user)
) -> None:
    """Route dependency: refuse the request unless ``authorization_error``
    allows it. Fails closed exactly like RBACMiddleware.
    """
    detail = authorization_error(request.app.router.routes, request.scope, user)
    if detail is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
