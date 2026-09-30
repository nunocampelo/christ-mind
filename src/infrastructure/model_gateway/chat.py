"""Gateway-backed `Complete` and `ChatStream` factories.

Routes LLM calls through the orchestration deployment, which accepts any model name
in the request body and dispatches to the right backend. This is the gateway
counterpart of `infrastructure.llm.anthropic_proxy` — same protocols, different
transport.
"""

import asyncio
import os
from collections.abc import AsyncIterator

from application.extraction.prompt import Complete
from application.mapping.prompt import PromptedSituationMapper
from infrastructure.llm.types import ChatStream
from infrastructure.model_gateway.client import (
    GatewayInferenceError,
    ModelGatewayClient,
)
from infrastructure.model_gateway.config import GatewayConfig, GatewayConfigError
from infrastructure.model_gateway.families.orchestration import OrchestrationFamily

_COMPLETION_PATH = "/completion"
_DEFAULT_MODEL = "gpt-4o"


class GatewayChatError(RuntimeError):
    """A gateway chat call failed."""


def _require_orchestration_url(config: GatewayConfig) -> str:
    if not config.orchestration_url:
        raise GatewayConfigError(
            "MODEL_GATEWAY_ORCHESTRATION_URL must be set for gateway chat"
        )
    return config.orchestration_url


def _chat_model() -> str:
    return os.getenv("MODEL_GATEWAY_CHAT_MODEL", "").strip() or _DEFAULT_MODEL


def make_complete(model: str | None = None) -> Complete:
    config = GatewayConfig.from_env()
    orch_url = _require_orchestration_url(config)
    client = ModelGatewayClient(config)
    family = OrchestrationFamily(model or _chat_model())

    def complete(system: str, user: str) -> str:
        body = family.build_request(system, user, stream=False)
        try:
            resp = client.post_orchestration(orch_url, _COMPLETION_PATH, body)
        except GatewayInferenceError as e:
            raise GatewayChatError("gateway chat request failed") from e
        return family.parse_response(resp)

    return complete


def make_chat_stream(model: str | None = None) -> ChatStream:
    config = GatewayConfig.from_env()
    orch_url = _require_orchestration_url(config)
    client = ModelGatewayClient(config)
    family = OrchestrationFamily(model or _chat_model())

    async def chat_stream(system: str, user: str) -> AsyncIterator[str]:
        body = family.build_request(system, user, stream=True)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        error: BaseException | None = None

        def _produce() -> None:
            nonlocal error
            try:
                for event in client.post_orchestration_stream(
                    orch_url, _COMPLETION_PATH, body
                ):
                    text = family.parse_stream_event(event)
                    if text is not None:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
            except BaseException as e:
                error = e
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        fut = loop.run_in_executor(None, _produce)
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item
        await fut
        if error is not None:
            raise GatewayChatError("gateway chat stream failed") from error

    return chat_stream


def make_mapper(model: str | None = None) -> PromptedSituationMapper:
    return PromptedSituationMapper(make_complete(model))
