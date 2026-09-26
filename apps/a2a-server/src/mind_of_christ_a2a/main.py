"""FastAPI host for the A2A transport over the Mind of Christ orchestrator.

One process to start: `python -m mind_of_christ_a2a.main` (or the `mind-of-christ-a2a`
script). It serves `POST /a2a` (native v1 JSON-RPC) and the v1 agent card. The agent
orchestrator is imported library code; the deterministic MCP tools are launched by the
orchestrator as a stdio subprocess per request — no separate server to start.

`AGENT_PUBLIC_URL` is required and read at startup: the agent card advertises this as the
`/a2a` endpoint's base, so it must be the URL clients actually reach. It fails loud at boot
rather than defaulting to a placeholder that would ship a wrong card.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from a2a.server.owner_resolver import resolve_user_scope
from a2a.server.tasks import DatabaseTaskStore, TaskStore
from a2a.types import AgentCard as CoreCard
from fastapi import FastAPI
from google.protobuf import json_format
from sqlalchemy.ext.asyncio import AsyncEngine

from infrastructure.config.env import load_env
from mind_of_christ_a2a.api.controllers import a2a_controller, agent_card_controller
from mind_of_christ_a2a.domain.a2a.agent_card import render_agent_card_v1
from mind_of_christ_a2a.infrastructure.db.engine import create_db_engine

load_env()

A2A_TASKS_TABLE = "a2a_tasks"


def _agent_public_url() -> str:
    url = os.getenv("AGENT_PUBLIC_URL", "").strip()
    if not url:
        raise RuntimeError("AGENT_PUBLIC_URL environment variable is not set")
    return url.rstrip("/")


async def build_task_store() -> tuple[TaskStore, AsyncEngine | None]:
    """Durable task store on the one shared engine, plus the engine to dispose on
    shutdown. create_table=False: Alembic owns the a2a_tasks DDL (see alembic/), so
    `alembic upgrade head` must run before this process starts. owner_resolver is passed
    explicitly to mark the per-user scoping seam — it resolves to "" today
    (unauthenticated), swappable when auth lands. Tests monkeypatch this to return an
    in-memory store (engine None), so the suite needs no database.
    """
    engine = create_db_engine()
    store = DatabaseTaskStore(
        engine,
        create_table=False,
        table_name=A2A_TASKS_TABLE,
        owner_resolver=resolve_user_scope,
    )
    await store.initialize()
    return store, engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    agent_url = _agent_public_url()
    card = render_agent_card_v1(agent_url)
    app.state.agent_card_v1 = card
    app.state.a2a_proto_card = cast(
        CoreCard, json_format.ParseDict(card, CoreCard())
    )
    store, engine = await build_task_store()
    app.state.a2a_task_store = store
    try:
        yield
    finally:
        if engine is not None:
            await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Mind of Christ Agent (A2A)", version="0.1.0", lifespan=lifespan)
    app.include_router(agent_card_controller.router)
    app.include_router(a2a_controller.router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
