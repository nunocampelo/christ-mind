"""Config for the model gateway, read from `MODEL_GATEWAY_*` at construction.

Fail-loud: `from_env` raises if any core var is unset — no silent placeholder, so
a misconfigured environment surfaces at startup, not as a confusing 401 mid-call.
The vendor name never appears here; only the neutral `MODEL_GATEWAY_*` names do.
"""

import os
from dataclasses import dataclass


class GatewayConfigError(RuntimeError):
    """A required MODEL_GATEWAY_* var is missing."""


_CORE_VARS = (
    "MODEL_GATEWAY_AUTH_URL",
    "MODEL_GATEWAY_CLIENT_ID",
    "MODEL_GATEWAY_CLIENT_SECRET",
    "MODEL_GATEWAY_BASE_URL",
    "MODEL_GATEWAY_RESOURCE_GROUP",
)


@dataclass(frozen=True)
class GatewayConfig:
    auth_url: str
    client_id: str
    client_secret: str
    base_url: str
    resource_group: str
    embedding_deployment_url: str | None
    orchestration_url: str | None

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        values: dict[str, str] = {}
        missing: list[str] = []
        for name in _CORE_VARS:
            v = os.getenv(name, "").strip()
            if not v:
                missing.append(name)
            values[name] = v
        if missing:
            raise GatewayConfigError(
                f"model gateway not configured: unset {', '.join(missing)}"
            )
        embed = os.getenv("MODEL_GATEWAY_EMBEDDING_DEPLOYMENT_URL", "").strip()
        orch = os.getenv("MODEL_GATEWAY_ORCHESTRATION_URL", "").strip()
        return cls(
            auth_url=values["MODEL_GATEWAY_AUTH_URL"].rstrip("/"),
            client_id=values["MODEL_GATEWAY_CLIENT_ID"],
            client_secret=values["MODEL_GATEWAY_CLIENT_SECRET"],
            base_url=values["MODEL_GATEWAY_BASE_URL"].rstrip("/"),
            resource_group=values["MODEL_GATEWAY_RESOURCE_GROUP"],
            embedding_deployment_url=(embed.rstrip("/") or None),
            orchestration_url=(orch.rstrip("/") or None),
        )

    @staticmethod
    def is_configured() -> bool:
        return all(os.getenv(name, "").strip() for name in _CORE_VARS)
