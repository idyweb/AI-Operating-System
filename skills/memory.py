"""
Memory skill — store and retrieve conversation history.
Why a skill: Any workflow can give Claude memory by importing this.
Not just Telegram — future workflows (web, API) get memory too.
"""
from typing import Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, desc

from core.config import get_settings
from db.memory import ConversationMemory

logger = structlog.get_logger()
settings = get_settings()

# Async engine for memory operations
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def save_message(
    chat_id: str,
    role: str,
    content: str,
    workflow_name: str = "telegram_message",
) -> None:
    """
    Save a message turn to conversation memory.
    Why fire-and-forget: Memory saving should never block
    the response from being sent to the user.
    """
    try:
        async with AsyncSessionLocal() as session:
            memory = ConversationMemory(
                chat_id=chat_id,
                role=role,
                content=content,
                workflow_name=workflow_name,
            )
            session.add(memory)
            await session.commit()
    except Exception as e:
        logger.error("memory.save_failed", error=str(e), chat_id=chat_id)


async def get_history(
    chat_id: str,
    limit: int = 10,
) -> list[dict[str, str]]:
    """
    Retrieve last N conversation turns for a chat.
    Returns in chronological order (oldest first) so Claude
    reads the conversation naturally.
    Why limit=10: Balances context richness vs token cost.
    10 turns = ~2000 tokens on average.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConversationMemory)
                .where(ConversationMemory.chat_id == chat_id)
                .where(ConversationMemory.is_deleted == False)
                .order_by(desc(ConversationMemory.created_at))
                .limit(limit)
            )
            messages = result.scalars().all()

            # Reverse to get chronological order
            messages = list(reversed(messages))

            return [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
    except Exception as e:
        logger.error("memory.get_failed", error=str(e), chat_id=chat_id)
        return []


async def clear_history(chat_id: str) -> None:
    """Clear all memory for a chat. Useful for /reset command."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ConversationMemory)
                .where(ConversationMemory.chat_id == chat_id)
            )
            messages = result.scalars().all()
            for msg in messages:
                await msg.soft_delete(session, commit=False)
            await session.commit()
            logger.info("memory.cleared", chat_id=chat_id)
    except Exception as e:
        logger.error("memory.clear_failed", error=str(e), chat_id=chat_id)