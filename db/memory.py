"""
Conversation memory model.
Why separate from TelegramMessage: TelegramMessage is for audit/ops.
ConversationMemory is optimized for retrieval — fast lookup by chat_id,
ordered by recency, with role/content structure Claude expects.
"""
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from db.base_model import BaseModel


class ConversationMemory(BaseModel):
    """
    Stores conversation history per chat for context injection.
    Why: Claude has no memory between calls. We fake it by
    storing and retrieving the last N turns per user.
    """
    __tablename__ = "conversation_memory"

    chat_id: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(20))  # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    workflow_name: Mapped[str] = mapped_column(String(100), default="telegram_message")

    __table_args__ = (
        Index("ix_memory_chat_created", "chat_id", "created_at"),
    )