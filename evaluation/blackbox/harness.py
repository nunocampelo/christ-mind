"""Brings up the live stack a black-box run needs, starting only what is down and tearing
down only what it started (a service already running is reused and left alone). Four
dependencies: the Anthropic proxy (`cproxy start`), Postgres (docker-compose), a separate
eval database + migrations, and the A2A server (a subprocess). The proxy holds real
credentials and is external -- it can be started but never torn down here.

This module is I/O and orchestration; it is exercised by the `--live` run, not unit-tested.
"""

import asyncio
import os
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_FILE = _REPO_ROOT / "apps/a2a-server/docker-compose.yml"
_ALEMBIC_INI = _REPO_ROOT / "apps/a2a-server/alembic.ini"
_EVAL_DB_NAME = "christ_mind_eval"
_DEFAULT_PROXY = "http://localhost:6656"


class HarnessError(RuntimeError):
    pass


@dataclass
class _Started:
    """What this run brought up, so cleanup only touches those. A reused service is absent
    from these flags and left running."""

    postgres: bool = False
    server_process: subprocess.Popen[bytes] | None = None
    cleanup: list[str] = field(default_factory=list)


@contextmanager
def live_stack(
    agent_url: str = "http://127.0.0.1:8766",
    proxy_url: str | None = None,
    stop_postgres_if_started: bool = False,
) -> Iterator[str]:
    """Yields the base URL an `A2AAgentClient` should hit, with the whole stack up.

    Postgres is shared infrastructure, so by default it is left running on teardown even if
    this run started it -- stopping a database container out from under the user is
    surprising and disruptive (it once stopped the dev server's Postgres). A container that
    was already running is never touched regardless. Pass `stop_postgres_if_started=True`
    only when you explicitly want a clean slate and know nothing else depends on it.
    """
    proxy_url = proxy_url or os.environ.get("ANTHROPIC_BASE_URL", _DEFAULT_PROXY)
    eval_db_url = _eval_db_url()
    started = _Started()
    try:
        _ensure_proxy(proxy_url)
        _ensure_postgres(eval_db_url, started)
        _ensure_eval_database(eval_db_url)
        _run_migrations(eval_db_url)
        _ensure_server(agent_url, eval_db_url, proxy_url, started)
        yield agent_url
    finally:
        _teardown(started, stop_postgres_if_started)


def _eval_db_url() -> str:
    base = os.environ.get("DATABASE_URL")
    if not base:
        raise HarnessError("DATABASE_URL must be set to derive the eval database URL")
    # Swap only the database segment, keep driver/creds/host/port.
    head, _, _tail = base.rpartition("/")
    return f"{head}/{_EVAL_DB_NAME}"


def _admin_db_url(any_db_url: str) -> str:
    # The `postgres` maintenance database always exists on a live server, so it's the safe
    # target for a liveness probe and for CREATE DATABASE.
    head, _, _tail = any_db_url.rpartition("/")
    return f"{head}/postgres"


def _ensure_proxy(proxy_url: str) -> None:
    if _http_ok(proxy_url):
        return
    _run(["cproxy", "start"], "could not start the Anthropic proxy (is cproxy on PATH?)")
    _wait_for(lambda: _http_ok(proxy_url), "Anthropic proxy", timeout=30.0)


def _ensure_postgres(eval_db_url: str, started: _Started) -> None:
    # Probe the always-present `postgres` admin database, NOT the eval database (which
    # doesn't exist yet on the first run) -- otherwise a Postgres that is already running is
    # misread as down, we start a container we didn't need, and teardown stops a server the
    # user was relying on. A running server is left untouched and never marked as ours.
    admin_url = _admin_db_url(eval_db_url)
    if _pg_reachable(admin_url):
        return
    _run(
        ["docker", "compose", "-f", str(_COMPOSE_FILE), "up", "-d"],
        "could not start Postgres via docker compose (is Docker running?)",
    )
    started.postgres = True
    _wait_for(lambda: _pg_reachable(admin_url), "Postgres", timeout=60.0)


def _ensure_eval_database(eval_db_url: str) -> None:
    if _pg_reachable(eval_db_url):
        return

    async def _create() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(_admin_db_url(eval_db_url)))
        try:
            await conn.execute(f'CREATE DATABASE "{_EVAL_DB_NAME}"')
        finally:
            await conn.close()

    asyncio.run(_create())


def _run_migrations(eval_db_url: str) -> None:
    env = {**os.environ, "DATABASE_URL": eval_db_url}
    _run(
        [".venv/bin/alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        "alembic migration of the eval database failed",
        env=env,
    )


def _ensure_server(
    agent_url: str, eval_db_url: str, proxy_url: str, started: _Started
) -> None:
    card = agent_url.rstrip("/") + "/.well-known/agent-card.json"
    if _http_ok(card):
        return
    host, port = _host_port(agent_url)
    env = {
        **os.environ,
        "DATABASE_URL": eval_db_url,
        "ANTHROPIC_BASE_URL": proxy_url,
        # Must be the eval server's own URL, not the repo .env's frontend-dev value,
        # or the agent card advertises the wrong /a2a endpoint.
        "AGENT_PUBLIC_URL": agent_url,
        "HOST": host,
        "PORT": str(port),
    }
    started.server_process = subprocess.Popen(
        [".venv/bin/python", "-m", "mind_of_christ_a2a.main"],
        cwd=str(_REPO_ROOT),
        env=env,
    )
    _wait_for(lambda: _http_ok(card), "A2A server", timeout=60.0)


def _teardown(started: _Started, stop_postgres_if_started: bool) -> None:
    if started.server_process is not None:
        started.server_process.terminate()
        try:
            started.server_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            started.server_process.kill()
    # Postgres is left running by default even when we started it (see live_stack docstring);
    # a container we found already running is never in `started.postgres` and never stopped.
    if started.postgres and stop_postgres_if_started:
        _run(
            ["docker", "compose", "-f", str(_COMPOSE_FILE), "down"],
            "failed to stop Postgres",
            check=False,
        )


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _pg_reachable(url: str) -> bool:
    """True iff a connection to the exact database in `url` succeeds. Callers probe a
    database expected to exist (the `postgres` admin db for liveness, the eval db to see if
    it's already created), so a missing-database error correctly reads as 'not reachable'."""

    async def _try() -> bool:
        try:
            conn = await asyncpg.connect(_asyncpg_dsn(url), timeout=3)
            await conn.close()
            return True
        except (OSError, asyncpg.PostgresError):
            return False

    return asyncio.run(_try())


def _asyncpg_dsn(sqlalchemy_url: str) -> str:
    # asyncpg wants a plain postgresql:// DSN, not SQLAlchemy's +asyncpg suffix.
    return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _host_port(url: str) -> tuple[str, int]:
    rest = url.split("://", 1)[-1]
    host, _, port = rest.partition(":")
    return host or "127.0.0.1", int(port or "8765")


def _wait_for(predicate, what: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1.0)
    raise HarnessError(f"{what} did not become ready within {timeout:.0f}s")


def _run(
    cmd: list[str], on_error: str, env: dict[str, str] | None = None, check: bool = True
) -> None:
    result = subprocess.run(cmd, cwd=str(_REPO_ROOT), env=env, capture_output=True)
    if check and result.returncode != 0:
        raise HarnessError(on_error)
