"""Durability of the DatabaseTaskStore, gated on a real database.

Skipped unless `DATABASE_URL` points at a Postgres with migrations applied
(`alembic upgrade head`), so the default `pytest` run needs no container. When it is set,
this proves what the InMemoryTaskStore can't: a task saved through one store instance is
retrievable — by id and by context_id — through a *separate* instance on a fresh engine,
i.e. it survives process restart, not just app lifetime.
"""

import os
import uuid

import pytest
from a2a.server.context import ServerCallContext
from a2a.server.tasks import DatabaseTaskStore
from a2a.types import ListTasksRequest, Task, TaskState, TaskStatus

from mind_of_christ_a2a.main import A2A_TASKS_TABLE
from mind_of_christ_a2a.infrastructure.db.engine import create_db_engine

pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not os.getenv("DATABASE_URL"),
        reason="DATABASE_URL not set; needs a migrated Postgres",
    ),
]


def _store() -> DatabaseTaskStore:
    return DatabaseTaskStore(
        create_db_engine(), create_table=False, table_name=A2A_TASKS_TABLE
    )


async def test_task_survives_a_fresh_store_instance() -> None:
    context_id = f"ctx-{uuid.uuid4()}"
    task_id = f"task-{uuid.uuid4()}"
    task = Task(
        id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
    )

    writer = _store()
    await writer.save(task, ServerCallContext())

    reader = _store()
    fetched = await reader.get(task_id, ServerCallContext())
    assert fetched is not None
    assert fetched.id == task_id
    assert fetched.context_id == context_id

    listed = await reader.list(
        ListTasksRequest(context_id=context_id), ServerCallContext()
    )
    assert [t.id for t in listed.tasks] == [task_id]

    await reader.delete(task_id, ServerCallContext())
