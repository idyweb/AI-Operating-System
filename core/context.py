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
    owner: str = "Iinyang"
    goal_annual_usd: int = 50000
    location_current: str = "Nigeria"
    location_target: str = "Canada"
    relocation_path: list[str] = Field(default_factory=lambda: [
        "Express Entry - Federal Skilled Worker",
        "Canadian university scholarship (AI/CS Masters or PhD)",
    ])
    active_income_streams: list[str] = Field(default_factory=lambda: [
        "AI Engineer - FMCG day job (600k NGN/month)",
        "Backend Dev - startup contract (450k NGN/month)",
    ])
    current_date: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    def as_system_prompt_fragment(self) -> str:
        return (
            f"You are the AI second brain for {self.owner}, currently based in {self.location_current}. "
            f"The mission has two pillars:\n"
            f"1. FINANCIAL: Generate ${self.goal_annual_usd:,} USD this year through: "
            f"{', '.join(self.active_income_streams)}.\n"
            f"2. RELOCATION: Move to {self.location_target} via: "
            f"{', '.join(self.relocation_path)}.\n"
            f"Today is {self.current_date}.\n"
            f"Every response must be ruthlessly practical and move one of these two needles. "
            f"Be direct, blunt, and production-grade in thinking. No fluff. No hand-holding. "
            f"Push hard toward both goals simultaneously where possible."
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