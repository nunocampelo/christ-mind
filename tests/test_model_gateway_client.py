import base64
import json
import time

import httpx
import pytest

from infrastructure.model_gateway.client import (
    GatewayAuthError,
    GatewayInferenceError,
    ModelGatewayClient,
)
from infrastructure.model_gateway.config import GatewayConfig, GatewayConfigError

_CORE = {
    "MODEL_GATEWAY_AUTH_URL": "https://auth.example/oauth/token/",
    "MODEL_GATEWAY_CLIENT_ID": "cid",
    "MODEL_GATEWAY_CLIENT_SECRET": "secret",
    "MODEL_GATEWAY_BASE_URL": "https://api.example/",
    "MODEL_GATEWAY_RESOURCE_GROUP": "default",
}


def _set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str | None) -> None:
    env = {**_CORE, **overrides}
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    monkeypatch.delenv("MODEL_GATEWAY_EMBEDDING_DEPLOYMENT_URL", raising=False)
    monkeypatch.delenv("MODEL_GATEWAY_ORCHESTRATION_URL", raising=False)


def _jwt(exp: float) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def test_config_from_env_reads_and_strips_trailing_slashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()
    assert cfg.auth_url == "https://auth.example/oauth/token"
    assert cfg.base_url == "https://api.example"
    assert cfg.resource_group == "default"
    assert cfg.embedding_deployment_url is None
    assert cfg.orchestration_url is None


def test_config_fail_loud_lists_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, MODEL_GATEWAY_CLIENT_SECRET=None)
    with pytest.raises(GatewayConfigError, match="MODEL_GATEWAY_CLIENT_SECRET"):
        GatewayConfig.from_env()


def test_config_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    assert GatewayConfig.is_configured() is True
    monkeypatch.delenv("MODEL_GATEWAY_AUTH_URL", raising=False)
    assert GatewayConfig.is_configured() is False


def _client_with(config: GatewayConfig, handler) -> ModelGatewayClient:
    client = ModelGatewayClient(config)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_token_minted_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()
    mints = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal mints
        if request.url.path == "/oauth/token":
            mints += 1
            assert request.headers["Authorization"].startswith("Basic ")
            assert b"grant_type=client_credentials" in request.content
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        return httpx.Response(200, json={"data": []})

    client = _client_with(cfg, handler)
    client.post_inference("https://api.example/dep", "/embeddings", {"input": []})
    client.post_inference("https://api.example/dep", "/embeddings", {"input": []})
    assert mints == 1


def test_token_remint_when_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()
    mints = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal mints
        if request.url.path == "/oauth/token":
            mints += 1
            return httpx.Response(200, json={"access_token": _jwt(time.time() - 10)})
        return httpx.Response(200, json={"data": []})

    client = _client_with(cfg, handler)
    client.post_inference("https://api.example/dep", "/embeddings", {"input": []})
    client.post_inference("https://api.example/dep", "/embeddings", {"input": []})
    assert mints == 2


def test_post_inference_sends_bearer_group_and_api_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        seen["auth"] = request.headers.get("Authorization")
        seen["group"] = request.headers.get("AI-Resource-Group")
        seen["api_version"] = request.url.params.get("api-version")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"embedding": [0.1]}]})

    client = _client_with(cfg, handler)
    out = client.post_inference(
        "https://api.example/dep", "/embeddings", {"input": ["x"]}
    )
    assert seen["auth"] == f"Bearer {client._token}"
    assert seen["group"] == "default"
    assert seen["api_version"] == "2023-05-15"
    assert seen["body"] == {"input": ["x"]}
    assert out == {"data": [{"embedding": [0.1]}]}


def test_auth_error_on_missing_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nope": 1})

    client = _client_with(cfg, handler)
    with pytest.raises(GatewayAuthError):
        client.post_inference("https://api.example/dep", "/embeddings", {})


def test_inference_error_on_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        return httpx.Response(404, json={"code": 404})

    client = _client_with(cfg, handler)
    with pytest.raises(GatewayInferenceError):
        client.post_inference("https://api.example/dep", "/embeddings", {})


# --- orchestration ---


def test_post_orchestration_sends_bearer_without_api_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        seen["auth"] = request.headers.get("Authorization")
        seen["group"] = request.headers.get("AI-Resource-Group")
        seen["has_api_version"] = "api-version" in request.url.params
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"orchestration_result": {"choices": []}})

    client = _client_with(cfg, handler)
    body = {"orchestration_config": {}, "input_params": {}}
    out = client.post_orchestration("https://api.example/orch", "/completion", body)
    assert seen["auth"] == f"Bearer {client._token}"
    assert seen["group"] == "default"
    assert seen["has_api_version"] is False
    assert seen["body"] == body
    assert out == {"orchestration_result": {"choices": []}}


def test_post_orchestration_raises_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        return httpx.Response(500)

    client = _client_with(cfg, handler)
    with pytest.raises(GatewayInferenceError, match="orchestration"):
        client.post_orchestration("https://api.example/orch", "/completion", {})


def test_post_orchestration_stream_yields_parsed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()
    sse_body = (
        'data: {"orchestration_result":{"choices":[{"delta":{"content":"Hello"}}]}}\n'
        "\n"
        'data: {"orchestration_result":{"choices":[{"delta":{"content":" world"}}]}}\n'
        "\n"
        "data: [DONE]\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        return httpx.Response(
            200,
            content=sse_body.encode(),
            headers={"content-type": "text/event-stream"},
        )

    client = _client_with(cfg, handler)
    events = list(
        client.post_orchestration_stream(
            "https://api.example/orch", "/completion", {}
        )
    )
    assert len(events) == 2
    assert events[0]["orchestration_result"]["choices"][0]["delta"]["content"] == "Hello"
    assert events[1]["orchestration_result"]["choices"][0]["delta"]["content"] == " world"


def test_post_orchestration_stream_skips_non_data_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()
    sse_body = (
        ": keep-alive\n"
        "\n"
        'data: {"orchestration_result":{"choices":[{"delta":{"content":"ok"}}]}}\n'
        "\n"
        "data: [DONE]\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        return httpx.Response(
            200,
            content=sse_body.encode(),
            headers={"content-type": "text/event-stream"},
        )

    client = _client_with(cfg, handler)
    events = list(
        client.post_orchestration_stream(
            "https://api.example/orch", "/completion", {}
        )
    )
    assert len(events) == 1


def test_post_orchestration_stream_raises_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    cfg = GatewayConfig.from_env()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _jwt(time.time() + 3600)})
        return httpx.Response(502)

    client = _client_with(cfg, handler)
    with pytest.raises(GatewayInferenceError, match="orchestration stream"):
        list(
            client.post_orchestration_stream(
                "https://api.example/orch", "/completion", {}
            )
        )
