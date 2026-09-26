"""ORM rows for conversation history (`Row` suffix per CLAUDE.md). `conversation_id` is
String(36) to match the A2A context_id width. `UNIQUE(conversation_id, sequence)` is the
guard `append_message` leans on so two concurrent appends can't share a sequence."""

from datetime import datetime

from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mind_of_christ_a2a.infrastructure.db.models.base import Base

_CONVERSATIONS = "conversations"
_MESSAGES = "conversation_messages"


class ConversationRow(Base):
    __tablename__ = _CONVERSATIONS

    conversation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    messages: Mapped[list["ConversationMessageRow"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ConversationMessageRow(Base):
    __tablename__ = _MESSAGES
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "sequence",
            name=f"uq_{_MESSAGES}_conversation_id_sequence",
        ),
        Index(
            f"ix_{_MESSAGES}_conversation_id_sequence", "conversation_id", "sequence"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey(f"{_CONVERSATIONS}.conversation_id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    conversation: Mapped[ConversationRow] = relationship(back_populates="messages")
