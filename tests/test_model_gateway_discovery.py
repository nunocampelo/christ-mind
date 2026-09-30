import time

import httpx
import pytest

from infrastructure.model_gateway.client import ModelGatewayClient
from infrastructure.model_gateway.config import GatewayConfig
from infrastructure.model_gateway.discovery import list_deployments

_CFG = GatewayConfig(
    auth_url="https://auth.example/oauth/token",
    client_id="cid",
    client_secret="secret",
    base_url="https://api.example",
    resource_group="default",
    embedding_deployment_url=None,
)

_CATALOG = {
    "resources": [
        {
            "id": "d1",
            "status": "RUNNING",
            "scenarioId": "foundation-models",
            "deploymentUrl": "https://api.example/v2/inference/deployments/d1",
            "details": {
                "resources": {"backend_details": {"model": {"name": "claude-4.8-opus"}}}
            },
        },
        {
            "id": "d2",
            "status": "RUNNING",
            "scenarioId": "foundation-models",
            "deploymentUrl": "https://api.example/v2/inference/deployments/d2",
            "details": {
                "resources": {
                    "backend_details": {"model": {"name": "text-embedding-3-large"}}
                }
            },
        },
    ]
}


def _client(handler) -> ModelGatewayClient:
    client = ModelGatewayClient(_CFG)
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def test_list_deployments_parses_and_flags_embedding() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _no_exp_token()})
        seen["path"] = request.url.path
        seen["group"] = request.headers.get("AI-Resource-Group")
        seen["api_version"] = request.url.params.get("api-version")
        return httpx.Response(200, json=_CATALOG)

    deployments = list_deployments(_client(handler), _CFG)
    assert seen["path"] == "/v2/lm/deployments"
    assert seen["group"] == "default"
    assert seen["api_version"] is None
    assert [d.id for d in deployments] == ["d1", "d2"]
    assert [d.is_embedding for d in deployments] == [False, True]
    assert deployments[1].deployment_url.endswith("/deployments/d2")


def _no_exp_token() -> str:
    # An opaque token forces a re-mint each process; fine for a one-shot list.
    return "opaque-token"


def test_list_deployments_empty_catalog() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oauth/token":
            return httpx.Response(200, json={"access_token": _no_exp_token()})
        return httpx.Response(200, json={"resources": []})

    assert list_deployments(_client(handler), _CFG) == []
