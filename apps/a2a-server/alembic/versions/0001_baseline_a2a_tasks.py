"""Baseline: a2a_tasks table matching a2a-sdk 1.1.2 DatabaseTaskStore.

Recreates the shape the a2a-sdk provisions via `Base.metadata.create_all()` in
`DatabaseTaskStore.initialize()` when `create_table=True` — but the app runs with
`create_table=False` (see main.py) so Alembic owns DDL. Columns mirror
`a2a.server.models.TaskMixin` (a2a-sdk 1.1.2). The two indexes match the SDK's
`index=True` on `id` (auto-named `ix_<table>_id`) and its `__table_args__` composite
index. The JSON column is named `metadata` in the DB — the SDK's ORM attribute
`task_metadata` maps to `name='metadata'` to avoid the Pydantic/SQLAlchemy conflict.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "a2a_tasks"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("context_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        sa.Column("status", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=True),
        sa.Column("history", sa.JSON(), nullable=True),
        sa.Column("protocol_version", sa.String(16), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )
    op.create_index(f"ix_{_TABLE}_id", _TABLE, ["id"])
    op.create_index(
        f"idx_{_TABLE}_owner_last_updated", _TABLE, ["owner", "last_updated"]
    )


def downgrade() -> None:
    op.drop_index(f"idx_{_TABLE}_owner_last_updated", table_name=_TABLE)
    op.drop_index(f"ix_{_TABLE}_id", table_name=_TABLE)
    op.drop_table(_TABLE)
