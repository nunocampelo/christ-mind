"""The one async SQLAlchemy engine, shared by every store on this server.

`DATABASE_URL` is required and read here — the A2A task store, the conversation
repository, and (later) the corpus all draw from this single engine, so the URL is picked
once. It fails loud if unset rather than defaulting to a placeholder that would silently
point at the wrong database. Both the app lifespan and Alembic's `env.py` import
`create_db_engine`, so migrations and the running app never disagree on the connection.
"""

import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    return url


def create_db_engine() -> AsyncEngine:
    return create_async_engine(database_url())
