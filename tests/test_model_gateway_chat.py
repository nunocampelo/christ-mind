import asyncio
from collections.abc import Iterator
from typing import Any

import pytest

from infrastructure.model_gateway.chat import (
    GatewayChatError,
    make_chat_stream,
    make_complete,
    make_mapper,
)
from infrastructure.model_gateway.client import ModelGatewayClient
from infrastructure.model_gateway.config import GatewayConfig, GatewayConfigError
from infrastructure.model_gateway.families.orchestration import OrchestrationFamily


_FAKE_CONFIG = GatewayConfig(
    auth_url="https://auth.example.com",
    client_id="id",
    client_secret="secret",
    base_url="https://gw.example.com",
    resource_group="rg",
    embedding_deployment_url=None,
    orchestration_url="https://gw.example.com/v2/inference/deployments/orch",
)


class _FakeClient:
    """Minimal fake that records what was called and returns canned responses."""

    def __init__(
        self,
        response: dict[str, Any] | None = None,
        stream_events: list[dict[str, Any]] | None = None,
    ) -> None:
        self._response = response or {}
        self._stream_events = stream_events or []
        self.last_call: tuple[str, str, dict[str, Any]] | None = None
        self.last_stream_call: tuple[str, str, dict[str, Any]] | None = None

    def post_orchestration(
        self, deployment_url: str, path: str, json_body: dict[str, Any]
    ) -> dict[str, Any]:
        self.last_call = (deployment_url, path, json_body)
        return self._response

    def post_orchestration_stream(
        self, deployment_url: str, path: str, json_body: dict[str, Any]
    ) -> Iterator[dict[str, Any]]:
        self.last_stream_call = (deployment_url, path, json_body)
        yield from self._stream_events


def _orch_response(text: str) -> dict[str, Any]:
    return {"orchestration_result": {"choices": [{"message": {"content": text}}]}}


def _orch_stream_events(*deltas: str) -> list[dict[str, Any]]:
    return [
        {"orchestration_result": {"choices": [{"delta": {"content": d}}]}}
        for d in deltas
    ]


def test_complete_calls_orchestration_and_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(response=_orch_response("Hello world"))
    family = OrchestrationFamily(model="gpt-4o")

    def complete(system: str, user: str) -> str:
        body = family.build_request(system, user, stream=False)
        resp = fake.post_orchestration(
            _FAKE_CONFIG.orchestration_url or "", "/completion", body
        )
        return family.parse_response(resp)

    assert complete("sys", "hi") == "Hello world"
    assert fake.last_call is not None
    assert fake.last_call[1] == "/completion"


def test_stream_yields_deltas() -> None:
    events = _orch_stream_events("Hello", " ", "world")
    fake = _FakeClient(stream_events=events)
    family = OrchestrationFamily(model="gpt-4o")

    async def _run() -> list[str]:
        body = family.build_request("sys", "hi", stream=True)
        deltas: list[str] = []
        for event in fake.post_orchestration_stream(
            _FAKE_CONFIG.orchestration_url or "", "/completion", body
        ):
            text = family.parse_stream_event(event)
            if text is not None:
                deltas.append(text)
        return deltas

    result = asyncio.run(_run())
    assert result == ["Hello", " ", "world"]


def test_make_complete_fails_without_orchestration_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_GATEWAY_AUTH_URL", "https://auth")
    monkeypatch.setenv("MODEL_GATEWAY_CLIENT_ID", "id")
    monkeypatch.setenv("MODEL_GATEWAY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MODEL_GATEWAY_BASE_URL", "https://gw")
    monkeypatch.setenv("MODEL_GATEWAY_RESOURCE_GROUP", "rg")
    monkeypatch.delenv("MODEL_GATEWAY_ORCHESTRATION_URL", raising=False)

    with pytest.raises(GatewayConfigError, match="ORCHESTRATION_URL"):
        make_complete()


def test_make_chat_stream_fails_without_orchestration_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_GATEWAY_AUTH_URL", "https://auth")
    monkeypatch.setenv("MODEL_GATEWAY_CLIENT_ID", "id")
    monkeypatch.setenv("MODEL_GATEWAY_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MODEL_GATEWAY_BASE_URL", "https://gw")
    monkeypatch.setenv("MODEL_GATEWAY_RESOURCE_GROUP", "rg")
    monkeypatch.delenv("MODEL_GATEWAY_ORCHESTRATION_URL", raising=False)

    with pytest.raises(GatewayConfigError, match="ORCHESTRATION_URL"):
        make_chat_stream()
