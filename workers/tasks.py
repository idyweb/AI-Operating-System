"""
Celery task definitions.
Why thin tasks: Tasks are just dispatchers — they resolve the workflow
class and call run(). All logic lives in workflows, not here.
"""
from typing import Any

import structlog
from celery import Task

from workers.celery_app import celery_app, run_async

import workflows.telegram_handler  # noqa: F401
import workflows.daily_briefing # noqa: F401

logger = structlog.get_logger()


class WorkflowTask(Task):
    """
    Base task class with structured logging and error handling.
    Why: Avoids repeating try/except and logging in every task.
    """
    abstract = True

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        logger.error(
            "task.failed",
            task_id=task_id,
            error=str(exc),
            exc_info=True,
        )

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: Any,
        kwargs: Any,
        einfo: Any,
    ) -> None:
        logger.warning(
            "task.retry",
            task_id=task_id,
            error=str(exc),
        )

    def on_success(
        self,
        retval: Any,
        task_id: str,
        args: Any,
        kwargs: Any,
    ) -> None:
        logger.info("task.success", task_id=task_id)


@celery_app.task(
    bind=True,
    base=WorkflowTask,
    name="workers.tasks.run_workflow",
    max_retries=3,
    default_retry_delay=60,
)
def run_workflow(self: Task, workflow_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """
    Generic task that runs any registered workflow by name.
    Why generic: One task definition handles all workflows.
    Adding a new workflow never requires a new Celery task.
    """
    from workflows.registry import get_workflow

    log = logger.bind(
        workflow=workflow_name,
        task_id=self.request.id,
    )

    log.info("task.start")

    try:
        workflow_class = get_workflow(workflow_name)
        workflow = workflow_class()
        context = run_async(workflow.run(input_data))

        return {
            "task_id": str(context.task_id),
            "workflow": workflow_name,
            "outputs": context.outputs,
            "errors": context.errors,
            "completed_nodes": context.completed_nodes,
        }

    except Exception as exc:
        log.error("task.error", error=str(exc))
        raise self.retry(exc=exc)