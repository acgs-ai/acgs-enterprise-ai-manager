"""
ACGS Enterprise Manager - FastAPI Main Application
Main entry point for the backend API server
"""

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
from typing import Optional

from backend.database import init_db, close_db
from backend.middleware.governance_interceptor import GovernanceMiddleware
from backend.middleware.auth import AuthMiddleware, api_docs_enabled, public_paths
from backend.auth.dependencies import get_current_user

# Import API routers
from backend.api import (
    tasks,
    recommendations,
    search,
    projects,
    assets,
    infrastructure,
    documents,
    financial,
    reports,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    logger.info("Starting ACGS Enterprise Manager API...")
    await init_db()
    logger.info("Database initialized successfully")

    yield

    # Shutdown
    logger.info("Shutting down ACGS Enterprise Manager API...")
    await close_db()
    logger.info("Database connections closed")


async def add_process_time_header(request: Request, call_next):
    """Add processing time to response headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions globally."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "type": "internal_error"},
    )


async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "acgs-enterprise-manager",
        "version": "1.0.0",
    }


def create_app(docs_enabled: Optional[bool] = None) -> FastAPI:
    """Build the application.

    ``docs_enabled`` defaults to the API_DOCS_ENABLED env var, read here at
    construction time. When false (the default), /docs, /redoc and
    /openapi.json are not served and are not on the public allowlist.
    """
    if docs_enabled is None:
        docs_enabled = api_docs_enabled()

    app = FastAPI(
        title="ACGS Enterprise Manager API",
        description="Enterprise AI Agent Management System with Constitutional Governance",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # Middleware order: Starlette runs the LAST-added middleware FIRST (outermost).
    # Resulting request flow: timing -> CORS -> Auth -> Governance -> routes.
    # Auth sits inside CORS so 401s carry CORS headers, and outside Governance so
    # unauthenticated requests never reach governance validation.
    # tests/integration/test_api_auth.py asserts this order.

    # Add governance interceptor middleware (innermost)
    app.add_middleware(GovernanceMiddleware)

    # Authentication: default-deny except the exact public allowlist
    app.add_middleware(AuthMiddleware, public_paths=public_paths(docs_enabled))

    # CORS middleware configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:8080",
        ],  # Frontend origins
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request timing middleware
    app.middleware("http")(add_process_time_header)

    # Global exception handler
    app.exception_handler(Exception)(global_exception_handler)

    # Health check endpoint
    app.get("/health", tags=["System"])(health_check)

    # Root endpoint
    @app.get("/", tags=["System"])
    async def root():
        """Root endpoint with API information."""
        info = {
            "message": "ACGS Enterprise Manager API",
            "version": "1.0.0",
            "health": "/health",
        }
        if docs_enabled:
            info["docs"] = "/docs"
        return info

    # Register API routers. Every /api/v1 router also depends on get_current_user
    # (defence in depth on top of AuthMiddleware).
    _auth = [Depends(get_current_user)]
    app.include_router(
        tasks.router, prefix="/api/v1/tasks", tags=["Tasks"], dependencies=_auth
    )
    app.include_router(
        recommendations.router,
        prefix="/api/v1/recommendations",
        tags=["Recommendations"],
        dependencies=_auth,
    )
    app.include_router(
        search.router, prefix="/api/v1/search", tags=["Search"], dependencies=_auth
    )
    app.include_router(
        projects.router,
        prefix="/api/v1/projects",
        tags=["Projects"],
        dependencies=_auth,
    )
    app.include_router(
        assets.router, prefix="/api/v1/assets", tags=["IT Assets"], dependencies=_auth
    )
    app.include_router(
        infrastructure.router,
        prefix="/api/v1/infrastructure",
        tags=["Infrastructure"],
        dependencies=_auth,
    )
    app.include_router(
        documents.router,
        prefix="/api/v1/documents",
        tags=["Documents"],
        dependencies=_auth,
    )
    app.include_router(
        financial.router,
        prefix="/api/v1/financial",
        tags=["Financial"],
        dependencies=_auth,
    )
    app.include_router(
        reports.router, prefix="/api/v1/reports", tags=["Reports"], dependencies=_auth
    )
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info"
    )
