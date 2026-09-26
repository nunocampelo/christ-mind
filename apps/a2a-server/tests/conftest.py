import pytest

from infrastructure.config.env import load_env

# Populate DATABASE_URL from .env for the whole session, exactly as an app entrypoint does.
# The DB-gated tests then decide to run or skip on a *live connection*, not on import order:
# without this, a file that doesn't import `main` (which calls load_env itself) would raise
# on create_db_engine() instead of skipping cleanly on a no-DB checkout.
load_env()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
