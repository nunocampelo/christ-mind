"""Conversation history tables (hand-written; target_metadata is None). The
(conversation_id, sequence) UNIQUE constraint is append_message's concurrency guard; the FK
is ON DELETE CASCADE so deleting a conversation drops its messages."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONVERSATIONS = "conversations"
_MESSAGES = "conversation_messages"


def upgrade() -> None:
    op.create_table(
        _CONVERSATIONS,
        sa.Column("conversation_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        _MESSAGES,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey(
                f"{_CONVERSATIONS}.conversation_id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence",
            name=f"uq_{_MESSAGES}_conversation_id_sequence",
        ),
    )
    op.create_index(
        f"ix_{_MESSAGES}_conversation_id_sequence",
        _MESSAGES,
        ["conversation_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index(f"ix_{_MESSAGES}_conversation_id_sequence", table_name=_MESSAGES)
    op.drop_table(_MESSAGES)
    op.drop_table(_CONVERSATIONS)
