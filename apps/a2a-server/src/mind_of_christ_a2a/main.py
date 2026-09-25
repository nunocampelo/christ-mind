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

from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard as CoreCard
from fastapi import FastAPI
from google.protobuf import json_format

from mind_of_christ_a2a.api.controllers import a2a_controller, agent_card_controller
from mind_of_christ_a2a.domain.a2a.agent_card import render_agent_card_v1


def _agent_public_url() -> str:
    url = os.getenv("AGENT_PUBLIC_URL", "").strip()
    if not url:
        raise RuntimeError("AGENT_PUBLIC_URL environment variable is not set")
    return url.rstrip("/")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    agent_url = _agent_public_url()
    card = render_agent_card_v1(agent_url)
    app.state.agent_card_v1 = card
    app.state.a2a_proto_card = cast(
        CoreCard, json_format.ParseDict(card, CoreCard())
    )
    # In-memory task store, app-lifetime, so a completed stream's task is retrievable
    # via GetTask. A durable store lands with a real deployment (roadmap).
    app.state.a2a_task_store = InMemoryTaskStore()
    yield


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
