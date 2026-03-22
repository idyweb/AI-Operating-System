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
    LLM-agnostic agent node via litellm.
    Supports any provider — Gemini, Anthropic, OpenRouter, Ollama.
    Switch models by changing LLM_MODEL in .env. Zero code changes.
    """

    def __init__(self) -> None:
        super().__init__()
        self.max_tokens = 8096
        self.model = self.settings.llm_model

    def get_system_prompt(self, context: TaskContext) -> str:
        return context.mission.as_system_prompt_fragment()

    def get_user_prompt(self, context: TaskContext) -> str:
        return str(context.input)

    def _set_provider_keys(self) -> None:
        """
        Set API keys as environment variables for litellm.
        Why: litellm reads keys from env vars per provider.
        """
        import os
        if self.settings.anthropic_api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.settings.anthropic_api_key
        if self.settings.openrouter_api_key:
            os.environ["OPENROUTER_API_KEY"] = self.settings.openrouter_api_key
        if self.settings.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self.settings.gemini_api_key

    async def _call_llm(self, model: str, system: str, user: str) -> str:
        """Call any LLM via litellm."""
        import litellm
        response = await litellm.acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content

    async def execute(self, context: TaskContext) -> TaskContext:
        """
        Try primary model first, fall back through fallback list.
        Injects conversation history if chat_id is in context input.
        """
        self._set_provider_keys()

        system = self.get_system_prompt(context)
        user = self.get_user_prompt(context)
        chat_id = context.input.get("chat_id")

        # Load conversation history if this is a chat-based workflow
        history: list[dict] = []
        if chat_id:
            from skills.memory import get_history, save_message
            history = await get_history(chat_id)
            # Save current user message
            await save_message(chat_id, "user", user)

        models_to_try = [self.model] + self.settings.fallback_models
        last_error = None

        for model in models_to_try:
            try:
                logger.info("llm.trying", model=model, node=self.name)

                # Build messages — history + current user message
                messages = history + [{"role": "user", "content": user}]

                import litellm
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    system=system,
                    max_tokens=self.max_tokens,
                )
                output = response.choices[0].message.content

                # Log cost
                try:
                    cost = litellm.completion_cost(completion_response=response)
                    logger.info(
                        "llm.cost",
                        model=model,
                        node=self.name,
                        input_tokens=response.usage.prompt_tokens,
                        output_tokens=response.usage.completion_tokens,
                        cost_usd=round(cost, 6),
                    )
                except Exception:
                    pass

                # Save assistant response to memory
                if chat_id:
                    await save_message(chat_id, "assistant", output)

                logger.info("llm.success", model=model, node=self.name)
                return context.with_output(self.name, output)

            except Exception as e:
                logger.warning("llm.failed", model=model, error=str(e))
                last_error = e
                continue

        return context.with_error(
            self.name,
            f"All LLM providers failed. Last error: {last_error}"
        )


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