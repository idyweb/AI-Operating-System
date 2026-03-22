"""
Celery application factory and task definitions.
Why separate from FastAPI: Celery workers run as independent processes.
They need their own app instance, not imported from the API layer.
"""
import asyncio
from typing import Any

import structlog
from celery import Celery
from celery.signals import worker_ready, worker_shutdown
from celery.schedules import crontab

from core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# --- App Factory ---

celery_app = Celery(
    "second_brain",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.tasks"],
)

celery_app.conf.update(
    # Serialization — JSON only, never pickle (security)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_track_started=True,
    task_acks_late=True,           # Only ack after task completes (no lost jobs)
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker (fair dispatch)

    # Results
    result_expires=86400,          # 24 hours

    # Retry defaults
    task_default_retry_delay=60,   # 60 seconds
    task_max_retries=3,

    # Beat schedule (Layer 2 — scheduled workflows)
    beat_schedule={
    "daily-briefing": {
        "task": "workers.tasks.run_workflow",
        "schedule": crontab(hour=7, minute=0),  # 7am UTC daily
        "kwargs": {
            "workflow_name": "daily_briefing",
            "input_data": {},
        },
    },
},
)


# --- Lifecycle Signals ---

@worker_ready.connect
def on_worker_ready(**kwargs: Any) -> None:
    """Log when worker comes online."""
    logger.info("celery.worker_ready")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs: Any) -> None:
    """Log when worker shuts down."""
    logger.info("celery.worker_shutdown")


# --- Async Helper ---

def run_async(coro: Any) -> Any:
    """
    Run an async coroutine from a sync Celery task.
    Why: Celery tasks are sync by default. Our workflows are async.
    This bridges the gap without running a persistent event loop per worker.
    """
    return asyncio.get_event_loop().run_until_complete(coro)