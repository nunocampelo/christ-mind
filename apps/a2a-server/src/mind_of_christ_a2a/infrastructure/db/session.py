"""The one place a session's commit/rollback/close boundary lives, so repositories can be
pure session-consumers instead of each re-implementing it. A caller opens a `unit_of_work`,
builds a session-bound repository inside it, and the block commits on clean exit or rolls
back on exception."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


class SessionProvider:
    def __init__(self, engine: AsyncEngine) -> None:
        self._session = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[AsyncSession]:
        async with self._session() as session:
            async with session.begin():
                yield session
