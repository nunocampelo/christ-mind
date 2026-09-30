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
