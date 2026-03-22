"""
Telegram skill — bot client, message sender, and auth guard.
Why a skill: Reusable across workflows. Any workflow can send
a Telegram message by importing this skill.
"""
import structlog
from telegram import Bot, Update
from telegram.constants import ParseMode

from core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


def get_bot() -> Bot:
    """Get configured Telegram bot instance."""
    return Bot(token=settings.telegram_bot_token)


def is_authorized(user_id: int) -> bool:
    """
    Check if a Telegram user is allowed to interact with the bot.
    Why: This is your personal AI OS — no one else should trigger it.
    """
    allowed = settings.allowed_user_ids
    if not allowed:
        logger.warning("telegram.no_allowed_users_configured")
        return False
    return user_id in allowed


async def send_message(
    chat_id: str | int,
    text: str,
    parse_mode: str = ParseMode.MARKDOWN,
) -> bool:
    """
    Send a message to a Telegram chat.
    Why returns bool: Callers need to know if delivery succeeded
    without crashing the workflow on Telegram failures.
    """
    try:
        bot = get_bot()
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
        )
        logger.info("telegram.message_sent", chat_id=chat_id)
        return True
    except Exception as e:
        logger.error("telegram.send_failed", error=str(e), chat_id=chat_id)
        return False


async def send_briefing(chat_id: str | int, briefing: str) -> bool:
    """
    Send a formatted daily briefing message.
    Splits long messages to respect Telegram's 4096 char limit.
    """
    max_length = 4096

    if len(briefing) <= max_length:
        return await send_message(chat_id, briefing)

    # Split into chunks without breaking markdown
    chunks = [briefing[i:i+max_length] for i in range(0, len(briefing), max_length)]
    results = []
    for chunk in chunks:
        result = await send_message(chat_id, chunk)
        results.append(result)

    return all(results)