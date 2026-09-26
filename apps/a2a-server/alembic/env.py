"""Alembic environment — async, online-only.

Builds the same async engine the app uses (`create_db_engine`, reading `DATABASE_URL`) and
runs migrations over a sync-wrapped connection. `target_metadata` is `None`: every
migration is hand-written (autogenerate stays off until there are ORM models worth
diffing against). `compare_type=True` is set so autogenerate is accurate the moment it's
turned on.
"""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from infrastructure.config.env import load_env
from mind_of_christ_a2a.infrastructure.db.engine import create_db_engine

load_env()

target_metadata = None


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_db_engine()
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


asyncio.run(run_async_migrations())
