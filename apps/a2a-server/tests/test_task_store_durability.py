"""Durability of the DatabaseTaskStore, gated on a reachable database.

This proves what the InMemoryTaskStore can't: a task saved through one store instance is
retrievable — by id and by context_id — after a simulated process restart, i.e. the task
lives in Postgres, not in the store's memory.

Gated on a *live connection*, not merely on `DATABASE_URL` being set: importing the app
runs `load_env()`, so `.env` makes `DATABASE_URL` present even on a checkout with no
Postgres running. The `_require_db` fixture opens a throwaway connection and skips the
test when the database is unreachable, so a no-DB checkout skips cleanly instead of failing
on connect. Bring the database up with
`docker compose -f apps/a2a-server/docker-compose.yml up -d` and apply migrations
(`alembic -c apps/a2a-server/alembic.ini upgrade head`) to run it.

The restart is simulated in-process: the SDK's `DatabaseTaskStore` defines its ORM model
on a *module-global* `Base.metadata` (a2a-sdk 1.1.2), so building a second store for the
same table name in one process would raise "Table already defined". A real restart is a
fresh process whose metadata starts empty; `_forget_task_table` reproduces that by dropping
the table from the SDK's metadata between the writer and the reader, so the reader
re-registers the model and connects on a fresh engine — reading only what Postgres holds.
"""

import uuid

import pytest
from a2a.server.context import ServerCallContext
from a2a.server.models import Base
from a2a.server.tasks import DatabaseTaskStore
from a2a.types import ListTasksRequest, Task, TaskState, TaskStatus
from sqlalchemy import text

from mind_of_christ_a2a.main import A2A_TASKS_TABLE
from mind_of_christ_a2a.infrastructure.db.engine import create_db_engine

pytestmark = pytest.mark.anyio


@pytest.fixture
async def _require_db() -> None:
    engine = create_db_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres unreachable; needs the compose database up + migrated")
    finally:
        await engine.dispose()


def _store() -> DatabaseTaskStore:
    return DatabaseTaskStore(
        create_db_engine(), create_table=False, table_name=A2A_TASKS_TABLE
    )


def _forget_task_table() -> None:
    table = Base.metadata.tables.get(A2A_TASKS_TABLE)
    if table is not None:
        Base.metadata.remove(table)


async def test_task_survives_a_simulated_restart(_require_db: None) -> None:
    # Bare UUIDs (36 chars): the SDK's TaskMixin pins id/context_id to String(36), so a
    # prefixed id would overflow the column — the ids the SDK actually assigns are UUIDs.
    context_id = str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
    )

    _forget_task_table()
    writer = _store()
    await writer.save(task, ServerCallContext())
    await writer.engine.dispose()

    _forget_task_table()
    reader = _store()
    try:
        fetched = await reader.get(task_id, ServerCallContext())
        assert fetched is not None
        assert fetched.id == task_id
        assert fetched.context_id == context_id

        listed = await reader.list(
            ListTasksRequest(context_id=context_id), ServerCallContext()
        )
        assert [t.id for t in listed.tasks] == [task_id]
    finally:
        await reader.delete(task_id, ServerCallContext())
        await reader.engine.dispose()
