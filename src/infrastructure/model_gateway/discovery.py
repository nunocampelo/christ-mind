"""Read-only introspection of the gateway's deployment catalog.

The gateway pins no embedding-deployment id anywhere in this repo (see the
increment plan), so a caller that wants one discovers it at runtime. Pure reads;
nothing here provisions or mutates a deployment.
"""

from dataclasses import dataclass
from typing import Any

from infrastructure.model_gateway.client import ModelGatewayClient
from infrastructure.model_gateway.config import GatewayConfig


@dataclass(frozen=True)
class Deployment:
    id: str
    status: str
    model_name: str
    scenario: str
    deployment_url: str

    @property
    def is_embedding(self) -> bool:
        return "embed" in self.model_name.lower()


def list_deployments(
    client: ModelGatewayClient, config: GatewayConfig
) -> list[Deployment]:
    data = client.get_json(config.base_url + "/v2/lm/deployments")
    resources = data.get("resources", [])
    return [_parse(d) for d in resources if isinstance(d, dict)]


def _parse(raw: dict[str, Any]) -> Deployment:
    details = raw.get("details") or {}
    resources = details.get("resources") or {}
    backend = resources.get("backend_details") or {}
    model = backend.get("model") or {}
    return Deployment(
        id=str(raw.get("id", "")),
        status=str(raw.get("status", "")),
        model_name=str(model.get("name", "")),
        scenario=str(raw.get("scenarioId", "")),
        deployment_url=str(raw.get("deploymentUrl", "")),
    )
