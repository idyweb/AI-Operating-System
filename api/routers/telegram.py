"""
Telegram webhook endpoint — Layer 1 trigger.
Why webhook over polling: Webhooks are push-based. No constant polling,
no wasted cycles. Telegram calls us when a message arrives.
"""
import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from telegram import Update

from core.config import get_settings
from skills.telegram import is_authorized, send_message
from workers.tasks import run_workflow

logger = structlog.get_logger()
router = APIRouter()
settings = get_settings()


def verify_webhook_secret(secret: str | None) -> bool:
    """
    Verify the request came from Telegram using webhook secret.
    Why: Anyone who finds your webhook URL could spam your bot.
    """
    if not settings.telegram_webhook_secret:
        return True  # Skip verification if not configured
    return secret == settings.telegram_webhook_secret


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Receive Telegram updates via webhook.
    Stores message in DB and dispatches to Celery immediately.
    Why background: We must respond to Telegram within 10 seconds
    or it will retry. Celery handles the actual processing.
    """
    # Verify secret token from Telegram header
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not verify_webhook_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    # Parse update
    body = await request.json()
    update = Update.de_json(body, None)

    if not update or not update.message:
        return {"ok": True}

    message = update.message
    user = message.from_user

    if not user:
        return {"ok": True}

    # Auth check — only you can use this
    if not is_authorized(user.id):
        logger.warning(
            "telegram.unauthorized",
            user_id=user.id,
            username=user.username,
        )
        await send_message(
            message.chat_id,
            "⛔ Unauthorized. This is a private AI OS.",
        )
        return {"ok": True}

    text = message.text or ""

    logger.info(
        "telegram.message_received",
        user_id=user.id,
        text=text[:50],
    )

    # Dispatch to Celery for processing
    background_tasks.add_task(
        _dispatch_telegram_workflow,
        chat_id=str(message.chat_id),
        user_id=str(user.id),
        username=user.username or "",
        text=text,
        message_id=str(message.message_id),
    )

    return {"ok": True}


async def _dispatch_telegram_workflow(
    chat_id: str,
    user_id: str,
    username: str,
    text: str,
    message_id: str,
) -> None:
    """Dispatch the telegram message workflow to Celery."""
    run_workflow.delay(
        workflow_name="telegram_message",
        input_data={
            "chat_id": chat_id,
            "user_id": user_id,
            "username": username,
            "text": text,
            "message_id": message_id,
        },
    )


@router.get("/telegram/webhook/info")
async def webhook_info() -> dict:
    """Check current webhook status with Telegram."""
    from telegram import Bot
    bot = Bot(token=settings.telegram_bot_token)
    info = await bot.get_webhook_info()
    return {
        "url": info.url,
        "pending_updates": info.pending_update_count,
        "last_error": info.last_error_message,
    }