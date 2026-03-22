"""
Workflow orchestrator — chains nodes together and manages execution.
Why: Central place to define how nodes connect, execute, and handle failures.
A workflow is the unit of work that Celery executes as a background job.
"""
from abc import ABC, abstractmethod
from typing import Any

import structlog
from langfuse import Langfuse

from core.config import get_settings
from core.context import TaskContext
from core.nodes import BaseNode

logger = structlog.get_logger()


class Workflow(ABC):
    """
    Base class for all workflows.
    A workflow is a named, ordered sequence of nodes that transforms
    an input payload into a result, tracked end-to-end via Langfuse.

    Usage:
        class MyWorkflow(Workflow):
            def build_nodes(self) -> list[BaseNode]:
                return [FetchNode(), AnalyzeNode(), SummarizeNode()]
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.name = self.__class__.__name__
        self._langfuse: Langfuse | None = None

        if self.settings.langfuse_public_key:
            try:
                self._langfuse = Langfuse(
                    public_key=self.settings.langfuse_public_key,
                    secret_key=self.settings.langfuse_secret_key,
                    host=self.settings.langfuse_host,
                )
                # v4: verify connection works
                self._langfuse.auth_check()
            except Exception as e:
                logger.warning("langfuse.init_failed", error=str(e))
                self._langfuse = None

    @abstractmethod
    def build_nodes(self) -> list[BaseNode]:
        """
        Define the ordered list of nodes for this workflow.
        Why method not class var: Allows dynamic node construction
        based on config or runtime conditions.
        """
        ...

    def _start_trace(self, context: TaskContext, input_data: dict[str, Any]) -> Any:
        """Langfuse v4 trace creation."""
        if not self._langfuse:
            return None
        try:
            return self._langfuse.start_trace(
                name=self.name,
                input=input_data,
                metadata={"mission_owner": context.mission.owner},
            )
        except Exception as e:
            logger.warning("langfuse.trace_failed", error=str(e))
            return None

    def _start_span(self, trace: Any, node_name: str) -> Any:
        """Langfuse v4 span creation."""
        if not trace:
            return None
        try:
            return trace.start_span(name=node_name)
        except Exception as e:
            logger.warning("langfuse.span_failed", error=str(e))
            return None

    def _end_span(self, span: Any, output: Any) -> None:
        """End a span safely."""
        if not span:
            return
        try:
            span.end(output=output)
        except Exception as e:
            logger.warning("langfuse.span_end_failed", error=str(e))

    def _end_trace(self, trace: Any, context: TaskContext) -> None:
        """Finalize trace with execution metadata."""
        if not trace:
            return
        try:
            trace.update(
                output=context.outputs,
                metadata={
                    "completed_nodes": context.completed_nodes,
                    "has_errors": context.has_errors,
                    "errors": context.errors,
                },
            )
        except Exception as e:
            logger.warning("langfuse.trace_end_failed", error=str(e))

    async def run(self, input_data: dict[str, Any]) -> TaskContext:
        """
        Execute all nodes in sequence, passing context through each.
        Why sequential by default: Most workflows have data dependencies
        between steps. Use ConcurrentWorkflow for independent steps.
        """
        context = TaskContext(
            workflow_name=self.name,
            input=input_data,
        )

        log = logger.bind(
            workflow=self.name,
            task_id=str(context.task_id),
        )

        trace = self._start_trace(context, input_data)
        if trace:
            context = context.model_copy(update={"trace_id": trace.id})

        log.info("workflow.start", input_keys=list(input_data.keys()))

        nodes = self.build_nodes()

        for node in nodes:
            if context.has_errors:
                log.warning(
                    "workflow.skipping_node",
                    node=node.name,
                    reason="previous node errored",
                )
                continue

            span = self._start_span(trace, node.name)
            context = await node(context)
            self._end_span(span, context.get_output(node.name))

        self._end_trace(trace, context)

        status = "workflow.error" if context.has_errors else "workflow.complete"
        log.info(
            status,
            completed_nodes=context.completed_nodes,
            errors=context.errors,
        )

        return context

    def get_final_output(self, context: TaskContext) -> Any:
        """
        Get the output of the last completed node.
        Why: Callers usually only care about the final result,
        not intermediate outputs.
        """
        if not context.completed_nodes:
            return None
        last_node = context.completed_nodes[-1]
        return context.get_output(last_node)