"""
Governance Interceptor Middleware
Intercepts AI operations and enforces ACGS-Lite governance rules
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import logging
import json
from typing import Callable

from backend.governance.acgs_integration import get_governance

logger = logging.getLogger(__name__)


class GovernanceMiddleware(BaseHTTPMiddleware):
    """
    Middleware to intercept and validate AI operations against governance rules.

    Implements the MACI pattern:
    - Monitor: Detect AI operations
    - Approve: Check if approval required
    - Control: Enforce governance decisions
    - Inspect: Log all decisions to audit trail
    """

    # Paths that trigger AI operation validation
    AI_OPERATION_PATHS = [
        "/api/v1/ai/",
        "/api/v1/recommendations/",
        "/api/v1/workflows/execute",
        "/api/v1/autonomous/",
    ]

    # Paths that are exempt from governance checks
    EXEMPT_PATHS = [
        "/health",
        "/docs",
        "/openapi.json",
        "/api/v1/auth/",
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Intercept requests and apply governance validation for AI operations.
        """
        path = request.url.path

        # Skip governance check for exempt paths
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS):
            return await call_next(request)

        # Check if this is an AI operation that needs governance validation
        is_ai_operation = any(
            path.startswith(ai_path) for ai_path in self.AI_OPERATION_PATHS
        )

        if is_ai_operation:
            # Extract operation details from request
            operation_context = await self._extract_operation_context(request)

            # Validate against governance rules
            governance = get_governance()
            validation_result = governance.validate_operation(
                operation=operation_context.get("operation", "unknown"),
                context=operation_context,
                agent_id=operation_context.get("agent_id", "default"),
            )

            # Enforce governance decision
            action = validation_result.get("action", "BLOCK")

            if action == "BLOCK":
                logger.warning(f"Governance blocked operation: {path}")
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "Operation blocked by governance rules",
                        "violations": validation_result.get("violations", []),
                        "decision_id": validation_result.get("decision_id"),
                    },
                )

            elif action == "REQUIRE_APPROVAL":
                logger.info(f"Governance requires approval for operation: {path}")

                # Request approval
                approval_request = governance.request_approval(
                    operation=operation_context.get("operation", "unknown"),
                    context=operation_context,
                    agent_id=operation_context.get("agent_id", "default"),
                )

                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Operation requires human approval",
                        "approval_request": approval_request,
                        "decision_id": validation_result.get("decision_id"),
                    },
                )

            # Action is ALLOW - proceed with request
            logger.info(f"Governance allowed operation: {path}")

            # Add governance decision to request state for downstream use
            request.state.governance_decision = validation_result

        # Proceed with the request
        response = await call_next(request)

        # Add governance headers to response
        if is_ai_operation and hasattr(request.state, "governance_decision"):
            decision = request.state.governance_decision
            response.headers["X-Governance-Decision"] = decision.get(
                "action", "UNKNOWN"
            )
            if "decision_id" in decision:
                response.headers["X-Governance-Decision-ID"] = decision["decision_id"]

        return response

    async def _extract_operation_context(self, request: Request) -> dict:
        """
        Extract operation context from request for governance validation.
        """
        context = {
            "path": request.url.path,
            "method": request.method,
            "operation": f"{request.method} {request.url.path}",
        }

        # Extract user/agent ID from headers or auth
        if "X-Agent-ID" in request.headers:
            context["agent_id"] = request.headers["X-Agent-ID"]

        # Extract request body for POST/PUT/PATCH
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    context["request_body"] = json.loads(body.decode())
            except Exception as e:
                logger.warning(f"Failed to parse request body: {e}")

        # Extract query parameters
        if request.query_params:
            context["query_params"] = dict(request.query_params)

        return context
