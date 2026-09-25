"""A2A JSON-RPC endpoint — thin delegation to the a2a-sdk dispatcher.

`POST /a2a` hands the raw request to `JsonRpcDispatcher.handle_requests`, which owns
parsing, method dispatch, and JSON-RPC error encoding. The dispatcher runs native v1
(`enable_v0_3_compat=False`, see api/dependencies), so the surface is `SendMessage` /
`GetTask` with proto-JSON bodies.
"""

from a2a.server.routes.jsonrpc_dispatcher import JsonRpcDispatcher
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from mind_of_christ_a2a.api.dependencies import get_a2a_dispatcher

router = APIRouter(tags=["a2a"])


@router.post("/a2a")
async def a2a(
    request: Request,
    dispatcher: JsonRpcDispatcher = Depends(get_a2a_dispatcher),
) -> Response:
    return await dispatcher.handle_requests(request)
