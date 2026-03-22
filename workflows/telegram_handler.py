"""
Telegram message handler workflow.
Receives a message, understands intent, routes to right action,
replies via Telegram. This is the brain behind the bot.
"""
from workflows.registry import register
from core.workflow import Workflow
from core.nodes import AgentNode, RouterNode, TransformNode
from core.context import TaskContext
from skills.telegram import send_message
from typing import Any


class UnderstandIntentNode(AgentNode):
    """
    Uses Claude to classify what the user wants.
    Why Claude for routing: Natural language intent is ambiguous.
    Claude handles typos, abbreviations, and context better than regex.
    """

    def get_system_prompt(self, context: TaskContext) -> str:
        base = context.mission.as_system_prompt_fragment()
        return f"""{base}

You are analyzing a Telegram message from your owner.
Classify the intent into one of these categories:
- RUN_WORKFLOW: owner wants to trigger a specific workflow
- ASK_QUESTION: owner is asking a question that needs a direct answer
- CAPTURE_IDEA: owner is capturing an idea or note
- STATUS_CHECK: owner wants to know status of something
- UNKNOWN: cannot classify

Respond ONLY with JSON in this exact format:
{{"intent": "CATEGORY", "workflow_name": "name_if_applicable", "summary": "brief summary"}}
"""

    def get_user_prompt(self, context: TaskContext) -> str:
        return f"Message: {context.input.get('text', '')}"


class RouteIntentNode(RouterNode):
    """Routes to the right handler based on classified intent."""

    def route(self, context: TaskContext) -> str:
        import json
        raw = context.get_output("UnderstandIntentNode") or "{}"
        try:
            data = json.loads(raw)
            intent = data.get("intent", "UNKNOWN")
        except Exception:
            intent = "UNKNOWN"

        routes = {
            "RUN_WORKFLOW": "RunRequestedWorkflow",
            "ASK_QUESTION": "AnswerQuestionNode",
            "CAPTURE_IDEA": "CaptureIdeaNode",
            "STATUS_CHECK": "StatusCheckNode",
            "UNKNOWN": "AnswerQuestionNode",
        }
        return routes.get(intent, "AnswerQuestionNode")


class AnswerQuestionNode(AgentNode):
    """Answers a direct question from the owner."""

    def get_system_prompt(self, context: TaskContext) -> str:
        base = context.mission.as_system_prompt_fragment()
        return f"""{base}

Answer the question directly and concisely.
You are responding via Telegram — keep it under 500 words.
Be blunt, precise, and practical. No fluff.
"""

    def get_user_prompt(self, context: TaskContext) -> str:
        return context.input.get("text", "")


class CaptureIdeaNode(AgentNode):
    """Acknowledges and formats an idea capture."""

    def get_system_prompt(self, context: TaskContext) -> str:
        return """You are capturing an idea for later processing.
Acknowledge the capture and suggest which context-hub area it belongs in:
0-identity, 1-inbox, 2-areas, 3-projects, 4-knowledge.
Keep response under 100 words."""

    def get_user_prompt(self, context: TaskContext) -> str:
        return f"Capture this idea: {context.input.get('text', '')}"


class StatusCheckNode(AgentNode):
    """Returns current status summary."""

    def get_system_prompt(self, context: TaskContext) -> str:
        base = context.mission.as_system_prompt_fragment()
        return f"""{base}

The owner wants a status update. Summarize:
- Current mission progress toward $50k goal
- Active projects status
- What should be prioritized today
Keep it under 200 words. Be direct.
"""

    def get_user_prompt(self, context: TaskContext) -> str:
        return "Give me a status update."


class SendReplyNode(TransformNode):
    """Sends the final response back via Telegram."""

    def transform(self, data: Any) -> Any:
        return data

    async def execute(self, context: TaskContext) -> TaskContext:
        import asyncio

        # Find the last meaningful output to send
        reply = (
            context.get_output("AnswerQuestionNode")
            or context.get_output("CaptureIdeaNode")
            or context.get_output("StatusCheckNode")
            or "✅ Done."
        )

        chat_id = context.input.get("chat_id", "")
        if chat_id:
            await send_message(chat_id, str(reply))

        return context.with_output(self.name, {"sent": True, "reply": str(reply)})


@register("telegram_message")
class TelegramMessageWorkflow(Workflow):
    """
    End-to-end Telegram message handler.
    Flow: understand intent → route → handle → reply
    """

    def build_nodes(self):
        return [
            UnderstandIntentNode(),
            RouteIntentNode(),
            AnswerQuestionNode(),
            SendReplyNode(),
        ]