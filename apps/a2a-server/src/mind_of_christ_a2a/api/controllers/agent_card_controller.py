"""Serves the v1 agent card at its well-known path so an A2A client can discover it."""

from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["a2a"])


@router.get("/.well-known/agent-card.json")
def agent_card(request: Request) -> JSONResponse:
    return JSONResponse(
        content=cast("dict[str, object]", request.app.state.agent_card_v1)
    )
