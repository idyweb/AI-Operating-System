"""
Workflow trigger endpoints — Layer 1 (webhook/API triggers).
Why thin routers: Zero business logic here.
Routers validate input and dispatch to Celery. That's it.
"""
import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from workflows.registry import get_workflow, list_workflows
from workers.tasks import run_workflow

logger = structlog.get_logger()
router = APIRouter()


class WorkflowRequest(BaseModel):
    workflow: str = Field(..., description="Registered workflow name")
    input: dict = Field(default_factory=dict, description="Input payload")
    async_run: bool = Field(default=True, description="Run async via Celery or sync")


class WorkflowResponse(BaseModel):
    task_id: str
    workflow: str
    status: str


@router.post("/workflows/run", response_model=WorkflowResponse)
async def trigger_workflow(request: WorkflowRequest) -> WorkflowResponse:
    """
    Trigger any registered workflow by name.
    async_run=True  → dispatches to Celery (default, non-blocking)
    async_run=False → runs inline (for testing/simple use cases)
    """
    # Validate workflow exists before dispatching
    try:
        get_workflow(request.workflow)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if request.async_run:
        # Dispatch to Celery — returns immediately
        task = run_workflow.delay(
            workflow_name=request.workflow,
            input_data=request.input,
        )
        logger.info(
            "workflow.dispatched",
            workflow=request.workflow,
            task_id=task.id,
        )
        return WorkflowResponse(
            task_id=task.id,
            workflow=request.workflow,
            status="queued",
        )
    else:
        # Run inline — blocks until complete
        workflow_class = get_workflow(request.workflow)
        workflow = workflow_class()
        context = await workflow.run(request.input)

        return WorkflowResponse(
            task_id=str(context.task_id),
            workflow=request.workflow,
            status="completed" if not context.has_errors else "failed",
        )


@router.get("/workflows")
async def list_available_workflows() -> dict:
    """List all registered workflows."""
    return {"workflows": list_workflows()}


@router.get("/workflows/status/{task_id}")
async def get_task_status(task_id: str) -> dict:
    """
    Check the status of a queued Celery task.
    Why: Async workflows need a polling endpoint so callers
    can check completion without webhooks.
    """
    from celery.result import AsyncResult
    from workers.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": result.status,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.get()
        else:
            response["error"] = str(result.result)

    return response