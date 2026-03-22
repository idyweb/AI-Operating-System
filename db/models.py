"""
Database models.
Why here: Single file imports ensure Alembic autogenerate
detects all models. Import this in env.py to register them.
"""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, String, Text, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base_model import BaseModel


class WorkflowRun(BaseModel):
    """
    Persists every workflow execution for audit, replay, and analytics.
    Why: Celery result backend gives us job status but loses context.
    We need the full TaskContext stored for debugging and replaying.
    """
    __tablename__ = "workflow_runs"

    workflow_name: Mapped[str] = mapped_column(String(100), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)

    # Full input/output stored as JSONB for queryability
    input_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    completed_nodes: Mapped[list] = mapped_column(JSONB, default=list)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Langfuse trace reference
    trace_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_workflow_runs_name_status", "workflow_name", "status"),
        Index("ix_workflow_runs_created", "created_at"),
    )


class Document(BaseModel):
    """
    Stores documents with vector embeddings for RAG.
    Why pgvector: Keeps everything in Postgres — no separate vector DB.
    1536 dims = OpenAI/Claude embedding size.
    """
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(50), index=True)

    # Vector embedding for semantic search — 1536 dims for Claude embeddings
    embedding: Mapped[Vector | None] = mapped_column(Vector(1536), nullable=True)

    # Metadata for filtering
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_documents_type", "doc_type"),
    )


class TelegramMessage(BaseModel):
    """
    Stores incoming Telegram messages for audit and async processing.
    Why persist: Messages can trigger long workflows. We store first,
    process async — never drop a user message.
    """
    __tablename__ = "telegram_messages"

    chat_id: Mapped[str] = mapped_column(String(100), index=True)
    message_id: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[str] = mapped_column(String(100), index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    processed: Mapped[bool] = mapped_column(default=False, index=True)
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_telegram_unprocessed", "processed", "created_at"),
    )