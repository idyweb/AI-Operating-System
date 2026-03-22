"""
FastAPI application factory.
Why factory pattern: Allows creating multiple app instances for testing
without side effects from module-level initialization.
"""
import importlib.metadata
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def _get_version() -> str:
    """
    Read version dynamically from pyproject.toml via package metadata.
    Why: Single source of truth — bump version in pyproject.toml
    and it reflects everywhere automatically. No hardcoding.
    """
    try:
        return importlib.metadata.version("second-brain")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0-dev"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application startup and shutdown.
    Why lifespan over on_event: on_event is deprecated in FastAPI 0.93+.
    Lifespan uses async context manager — cleaner, explicit, and testable.
    Everything before yield runs on startup, after yield on shutdown.
    """
    logger.info("api.startup", env=settings.app_env, version=_get_version())
    yield
    logger.info("api.shutdown")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    Why: Separating creation from module-level instantiation
    makes the app testable and avoids circular imports.
    """
    app = FastAPI(
        title="Second Brain API",
        description="Personal AI Operating System — v2 of you, but tireless.",
        version=_get_version(),
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
    )

    # CORS — restrict in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers

    from api.routers import health, workflows, telegram
    app.include_router(telegram.router, prefix="/api/v1", tags=["telegram"])
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(workflows.router, prefix="/api/v1", tags=["workflows"])

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(
            "unhandled_exception",
            error=str(exc),
            path=str(request.url),
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app


app = create_app()