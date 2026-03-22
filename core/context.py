"""
TaskContext: The state object passed between every node in a workflow.
Why Pydantic: Validates data at every boundary, gives us free serialization
for Celery task passing and Langfuse tracing.
"""
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MissionContext(BaseModel):
    """
    Injected into every workflow so Claude always knows the north star.
    Why: Every AI call should be oriented toward your actual goals —
    not just completing a task in isolation.
    """
    owner: str = "iinyang"
    goal_annual_usd: int = 50000
    active_income_streams: list[str] = Field(default_factory=lambda: [
        "AI Engineer - FMCG day job",
        "Backend Dev - startup contract",
    ])
    current_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    def as_system_prompt_fragment(self) -> str:
        """
        Why: Gives Claude the mission context in natural language
        so it can prioritize and frame responses accordingly.
        """
        return (
            f"You are acting as a second brain for {self.owner}. "
            f"The mission is to generate ${self.goal_annual_usd:,} this year "
            f"through: {', '.join(self.active_income_streams)}. "
            f"Today is {self.current_date}. "
            "Every response should provide real value toward this mission — "
            "be precise, production-ready, and ruthlessly practical."
        )


class TaskContext(BaseModel):
    """
    Immutable-by-convention state object flowing through a workflow.
    Each node reads from it and returns an updated copy — never mutates in place.
    Why: Predictable data flow. Easy to log, trace, and debug.
    """
    # Identity
    task_id: UUID = Field(default_factory=uuid4)
    workflow_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Mission
    mission: MissionContext = Field(default_factory=MissionContext)

    # Input payload — what triggered this workflow
    input: dict[str, Any] = Field(default_factory=dict)

    # Accumulated outputs from each node
    outputs: dict[str, Any] = Field(default_factory=dict)

    # Execution metadata
    current_node: str = ""
    completed_nodes: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    trace_id: str | None = None

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def with_output(self, node_name: str, output: Any) -> "TaskContext":
        """
        Returns a new TaskContext with the node output recorded.
        Why immutable update: Preserves history of what each node produced.
        Makes debugging trivial — you can replay any step.
        """
        return self.model_copy(update={
            "outputs": {**self.outputs, node_name: output},
            "completed_nodes": [*self.completed_nodes, node_name],
            "current_node": node_name,
        })

    def with_error(self, node_name: str, error: str) -> "TaskContext":
        """Records an error without killing the workflow — fail gracefully."""
        return self.model_copy(update={
            "errors": [
                *self.errors,
                {
                    "node": node_name,
                    "error": error,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            ],
        })

    def get_output(self, node_name: str) -> Any | None:
        """Safe output retrieval — returns None instead of KeyError."""
        return self.outputs.get(node_name)