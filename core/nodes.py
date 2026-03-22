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
    A node that calls an LLM to do intelligent work.
    Supports Anthropic direct or OpenRouter (free models).
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_tokens = 8096
        self.model = self.settings.llm_model

        # Use OpenRouter if configured, else fall back to Anthropic
        if self.settings.openrouter_api_key:
            import httpx
            self._client_type = "openrouter"
        elif self.settings.anthropic_api_key and not self.settings.anthropic_api_key.startswith("sk-ant-..."):
            self._client_type = "anthropic"
        else:
            self._client_type = "none"

    def get_system_prompt(self, context: TaskContext) -> str:
        return context.mission.as_system_prompt_fragment()

    def get_user_prompt(self, context: TaskContext) -> str:
        return str(context.input)

    async def _call_openrouter(self, system: str, user: str) -> str:
        """
        Call OpenRouter with automatic model fallback.
        Why fallback: Free models have rate limits and occasional downtime.
        Loop through until one succeeds.
        """
        import httpx

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/second-brain",
            "X-Title": "Second Brain",
        }

        # Use configured model or loop through free models
        models_to_try = (
            [self.settings.llm_model]
            if self.settings.llm_model
            else self.settings.free_models
        )

        last_error = None

        async with httpx.AsyncClient(timeout=60.0) as client:
            for model in models_to_try:
                try:
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "max_tokens": self.max_tokens,
                    }

                    logger.info("openrouter.trying_model", model=model)

                    response = await client.post(
                        f"{self.settings.openrouter_base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]

                    logger.info("openrouter.success", model=model)
                    return content

                except Exception as e:
                    logger.warning(
                        "openrouter.model_failed",
                        model=model,
                        error=str(e),
                    )
                    last_error = e
                    continue

        raise Exception(f"All models failed. Last error: {last_error}")
    async def _call_anthropic(self, system: str, user: str) -> str:
        """Call Anthropic API directly."""
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=self.settings.anthropic_api_key)
        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text

    async def execute(self, context: TaskContext) -> TaskContext:
        system = self.get_system_prompt(context)
        user = self.get_user_prompt(context)

        if self._client_type == "openrouter":
            output = await self._call_openrouter(system, user)
        elif self._client_type == "anthropic":
            output = await self._call_anthropic(system, user)
        else:
            output = "No LLM provider configured. Add ANTHROPIC_API_KEY or OPENROUTER_API_KEY to .env"

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