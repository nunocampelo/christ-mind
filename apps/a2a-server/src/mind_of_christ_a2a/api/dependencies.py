"""Composition root: build the SDK JSON-RPC dispatcher for the /a2a endpoint.

`get_a2a_dispatcher` is the seam tests override (`app.dependency_overrides`): swap the
executor for one whose orchestrator is stubbed, and no MCP subprocess or real LLM is
touched. `enable_v0_3_compat=False` serves the native v1 surface (`SendMessage`,
`GetTask`), per the agent-layer plan.

The task store is an app-lifetime singleton (built in the main.py lifespan, read from
app.state) so a completed stream's task is retrievable via `GetTask`. The proto agent card
is likewise built once at startup.

`get_conversations` yields a per-request repository bound to one unit of work, so a request
that touches the repo twice (e.g. rename-then-read) shares a transaction. The executor is
not a request, so it holds the `SessionProvider` and opens its own short unit of work per
append (the provider is built once at startup, read from app.state).
"""

from collections.abc import AsyncIterator
from typing import cast

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from a2a.server.tasks import TaskStore
from a2a.types import AgentCard as CoreCard
from fastapi import Request

from mind_of_christ_a2a.domain.a2a.executor import MindOfChristExecutor
from mind_of_christ_a2a.infrastructure.db.repositories.conversations import (
    ConversationRepository,
)
from mind_of_christ_a2a.infrastructure.db.session import SessionProvider


def build_executor(sessions: SessionProvider) -> MindOfChristExecutor:
    return MindOfChristExecutor(sessions=sessions)


def get_a2a_task_store(request: Request) -> TaskStore:
    return cast(TaskStore, request.app.state.a2a_task_store)


async def get_conversations(request: Request) -> AsyncIterator[ConversationRepository]:
    provider = cast(SessionProvider, request.app.state.session_provider)
    async with provider.unit_of_work() as session:
        yield ConversationRepository(session)


def get_session_provider(request: Request) -> SessionProvider:
    return cast(SessionProvider, request.app.state.session_provider)


def get_a2a_proto_card(request: Request) -> CoreCard:
    return cast(CoreCard, request.app.state.a2a_proto_card)


def get_a2a_dispatcher(request: Request) -> JsonRpcDispatcher:
    handler = DefaultRequestHandler(
        agent_executor=build_executor(get_session_provider(request)),
        task_store=get_a2a_task_store(request),
        agent_card=get_a2a_proto_card(request),
    )
    return JsonRpcDispatcher(handler, enable_v0_3_compat=False)
