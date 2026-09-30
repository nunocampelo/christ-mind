"""Low-level HTTP client for the model gateway: OAuth token mint + inference POST.

Raw `httpx`, no vendor SDK (see the increment plan). Knows OAuth and how to sign a
request; knows *nothing* about model shapes — `embedder.py` owns the embed body and
response parsing. The token is minted lazily and cached until near its JWT expiry.

The two gateway-specific wire details the plan flagged as unavoidable live here,
each marked: the resource-group request header, and the `api-version` query param
inference calls require. They stay inside this module so no public name leaks them.
"""

import base64
import binascii
import json
import time
from typing import Any

import httpx

from infrastructure.model_gateway.config import GatewayConfig

# Gateway contract: inference endpoints reject a call without this query param
# (returns 404). Kept here, not in a public name. Bump only if the gateway does.
_INFERENCE_API_VERSION = "2023-05-15"

# Gateway contract: the resource group travels as this request header.
_RESOURCE_GROUP_HEADER = "AI-Resource-Group"

_TOKEN_EXPIRY_SKEW_SEC = 60.0


class GatewayAuthError(RuntimeError):
    """Token mint failed or returned no usable access_token."""


class GatewayInferenceError(RuntimeError):
    """An inference POST failed or returned a non-JSON body."""


class ModelGatewayClient:
    def __init__(self, config: GatewayConfig, timeout: float = 120.0) -> None:
        self._config = config
        self._http = httpx.Client(timeout=timeout)
        self._token: str | None = None
        self._token_exp: float = 0.0

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ModelGatewayClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _mint_token(self) -> tuple[str, float]:
        try:
            resp = self._http.post(
                self._config.auth_url,
                data={"grant_type": "client_credentials"},
                auth=(self._config.client_id, self._config.client_secret),
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise GatewayAuthError("model gateway token request failed") from e
        except json.JSONDecodeError as e:
            raise GatewayAuthError("model gateway auth response was not JSON") from e

        token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise GatewayAuthError("no access_token in model gateway auth response")
        return token, _jwt_exp(token)

    def _bearer(self) -> str:
        now = time.time()
        if self._token is None or now >= self._token_exp - _TOKEN_EXPIRY_SKEW_SEC:
            self._token, self._token_exp = self._mint_token()
        return self._token

    def get_json(self, url: str) -> dict[str, Any]:
        """A signed GET against a full gateway URL (e.g. the deployments catalog).
        Carries the same bearer + resource-group header as inference, but no
        `api-version` — that param is inference-only."""
        headers = {
            "Authorization": f"Bearer {self._bearer()}",
            _RESOURCE_GROUP_HEADER: self._config.resource_group,
        }
        try:
            resp = self._http.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise GatewayInferenceError("model gateway GET failed") from e
        except json.JSONDecodeError as e:
            raise GatewayInferenceError("model gateway response was not JSON") from e
        if not isinstance(data, dict):
            raise GatewayInferenceError("model gateway response was not a JSON object")
        return data

    def post_inference(
        self, deployment_url: str, path: str, json_body: dict[str, Any]
    ) -> dict[str, Any]:
        url = deployment_url.rstrip("/") + path
        headers = {
            "Authorization": f"Bearer {self._bearer()}",
            _RESOURCE_GROUP_HEADER: self._config.resource_group,
            "Content-Type": "application/json",
        }
        try:
            resp = self._http.post(
                url,
                headers=headers,
                params={"api-version": _INFERENCE_API_VERSION},
                json=json_body,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise GatewayInferenceError("model gateway inference request failed") from e
        except json.JSONDecodeError as e:
            raise GatewayInferenceError("model gateway response was not JSON") from e
        if not isinstance(data, dict):
            raise GatewayInferenceError("model gateway response was not a JSON object")
        return data


def _jwt_exp(token: str) -> float:
    """Read the JWT `exp` claim so the token cache can refresh before expiry.
    An opaque (non-JWT) token has no readable exp; treat it as already expired so
    every call re-mints rather than trusting a stale token."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, binascii.Error, json.JSONDecodeError):
        return 0.0
    exp = claims.get("exp") if isinstance(claims, dict) else None
    return float(exp) if isinstance(exp, (int, float)) else 0.0
