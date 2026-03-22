"""
Daily briefing workflow — Layer 2 (scheduled).
Runs every morning, summarizes your day, priorities, and mission progress.
Delivered straight to your Telegram.
"""
from typing import Any

from workflows.registry import register
from core.workflow import Workflow
from core.nodes import AgentNode, TransformNode
from core.context import TaskContext
from skills.telegram import send_briefing
from core.config import get_settings


class GatherContextNode(TransformNode):
    """
    Collects all context needed for the briefing.
    Why separate node: Context gathering should be isolated from
    generation — easy to extend with DB queries, API calls later.
    """

    def transform(self, data: Any) -> Any:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        return {
            "date": now.strftime("%A, %B %d %Y"),
            "time": now.strftime("%H:%M UTC"),
            "day_of_week": now.strftime("%A"),
            "week_number": now.isocalendar()[1],
        }


class GenerateBriefingNode(AgentNode):
    """
    Generates the daily briefing using Claude.
    Knows your mission, income streams, and current date.
    """

    def get_system_prompt(self, context: TaskContext) -> str:
        base = context.mission.as_system_prompt_fragment()
        return f"""{base}

You are generating a daily morning briefing for your owner.
Format it for Telegram using markdown.

Structure it exactly like this:

*🌅 Daily Briefing — [DATE]*

*💰 Mission Tracker*
- Goal: $50,000 this year
- Income streams: [list them]
- Focus: What moves the needle today?

*🎯 Top 3 Priorities*
1. [Most important task — day job]
2. [Most important task — startup contract]
3. [Most important task — second-brain build]

*⚡ Today's Power Move*
[One specific, high-leverage action that compounds toward the $50k goal]

*🧠 Engineering Insight*
[One sharp technical insight relevant to current work]

*📊 Momentum Check*
[Brief honest assessment — are we on track?]

Be direct. No fluff. Every word must earn its place.
"""

    def get_user_prompt(self, context: TaskContext) -> str:
        ctx = context.get_output("GatherContextNode") or {}
        return (
            f"Generate my daily briefing for {ctx.get('date', 'today')}. "
            f"It's {ctx.get('day_of_week', 'a weekday')}, week {ctx.get('week_number', '')}."
        )


class DeliverBriefingNode(TransformNode):
    """Delivers the briefing to Telegram."""

    def transform(self, data: Any) -> Any:
        return data

    async def execute(self, context: TaskContext) -> TaskContext:
        settings = get_settings()
        briefing = context.get_output("GenerateBriefingNode") or ""
        chat_id = context.input.get("chat_id") or settings.allowed_telegram_user_ids

        if not chat_id:
            return context.with_error(self.name, "No chat_id configured")

        success = await send_briefing(chat_id, briefing)
        return context.with_output(self.name, {
            "delivered": success,
            "chat_id": chat_id,
        })


@register("daily_briefing")
class DailyBriefingWorkflow(Workflow):
    """
    Morning briefing — runs on schedule via Celery Beat.
    Can also be triggered manually via Telegram or API.
    """

    def build_nodes(self):
        return [
            GatherContextNode(),
            GenerateBriefingNode(),
            DeliverBriefingNode(),
        ]