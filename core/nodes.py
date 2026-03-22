"""
Base node abstractions for the workflow engine.
Why ABC: Enforces the contract that every node must implement execute().
Every node is stateless — all state lives in TaskContext.
"""
from abc import ABC, abstractmethod
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from core.config import get_settings
from core.context import TaskContext

logger = structlog.get_logger()


class BaseNode(ABC):
    """
    The atomic unit of work in a workflow.
    Why stateless: Nodes can be retried, parallelized, and reused
    across different workflows without side effects.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.name = self.__class__.__name__

    @abstractmethod
    async def execute(self, context: TaskContext) -> TaskContext:
        """
        Execute this node's logic and return updated context.
        Never mutates context — always returns context.with_output(...)
        """
        ...

    async def __call__(self, context: TaskContext) -> TaskContext:
        """
        Wraps execute() with logging and error handling.
        Why: Every node gets tracing for free without repeating boilerplate.
        """
        log = logger.bind(
            node=self.name,
            workflow=context.workflow_name,
            task_id=str(context.task_id),
        )

        log.info("node.start")
        try:
            result = await self.execute(context)
            log.info("node.complete")
            return result
        except Exception as e:
            log.error("node.error", error=str(e))
            return context.with_error(self.name, str(e))


class AgentNode(BaseNode):
    """
    A node that calls Claude to do intelligent work.
    Why separate from BaseNode: Not all nodes need an LLM —
    some just transform data, call APIs, or route logic.
    """

    def __init__(self) -> None:
        super().__init__()
        self.client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        self.model = "claude-sonnet-4-5"
        self.max_tokens = 8096

    def get_system_prompt(self, context: TaskContext) -> str:
        """
        Override in subclasses to customize the system prompt.
        Base implementation injects mission context automatically.
        """
        return context.mission.as_system_prompt_fragment()

    def get_user_prompt(self, context: TaskContext) -> str:
        """Override in subclasses to build the user message."""
        return str(context.input)

    async def execute(self, context: TaskContext) -> TaskContext:
        """
        Calls Claude with mission context + node-specific prompts.
        Why structured this way: Separating system/user prompt construction
        into overridable methods makes subclassing clean and testable.
        """
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self.get_system_prompt(context),
            messages=[
                {"role": "user", "content": self.get_user_prompt(context)}
            ],
        )

        output = response.content[0].text
        return context.with_output(self.name, output)


class RouterNode(BaseNode):
    """
    Decides which node to execute next based on context.
    Why: Conditional branching without hardcoding workflow logic.
    """

    @abstractmethod
    def route(self, context: TaskContext) -> str:
        """Return the name of the next node to execute."""
        ...

    async def execute(self, context: TaskContext) -> TaskContext:
        next_node = self.route(context)
        return context.with_output(self.name, {"next_node": next_node})


class TransformNode(BaseNode):
    """
    A node that transforms data without calling an LLM.
    Use for: parsing, formatting, filtering, enriching data.
    """

    @abstractmethod
    def transform(self, data: Any) -> Any:
        """Pure transformation — no async, no side effects."""
        ...

    async def execute(self, context: TaskContext) -> TaskContext:
        result = self.transform(context.input)
        return context.with_output(self.name, result)