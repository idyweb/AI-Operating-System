"""
Health check endpoints.
Why: Docker, load balancers, and monitoring all need a reliable
liveness and readiness signal.
"""
import asyncio
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from core.config import get_settings

logger = structlog.get_logger()
router = APIRouter()
settings = get_settings()


class HealthResponse(BaseModel):
    status: str
    env: str
    timestamp: str
    checks: dict[str, str]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Liveness probe — is the API process alive?
    Returns 200 if the app is running regardless of dependency health.
    """
    return HealthResponse(
        status="ok",
        env=settings.app_env,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks={"api": "ok"},
    )


@router.get("/health/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """
    Readiness probe — are all dependencies healthy?
    Returns 200 only if Redis and Postgres are reachable.
    Why separate from liveness: A container can be alive but not ready
    (e.g. DB still starting). K8s and Docker use both signals.
    """
    checks: dict[str, str] = {}

    # Check Redis
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        await asyncio.wait_for(r.ping(), timeout=2.0)
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"

    # Check Postgres
    try:
        import asyncpg
        conn = await asyncio.wait_for(
            asyncpg.connect(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
            ),
            timeout=2.0,
        )
        await conn.close()
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"

    return HealthResponse(
        status=overall,
        env=settings.app_env,
        timestamp=datetime.now(timezone.utc).isoformat(),
        checks=checks,
    )