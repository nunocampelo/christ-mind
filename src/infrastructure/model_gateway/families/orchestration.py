"""The orchestration family — routes to any model via the orchestration deployment.

Unlike `foundation-models` deployments (one per model, `/chat/completions`), the
orchestration deployment is a model-router: the model name travels in the request
body, and the endpoint is `/completion` with no `api-version` query param. The
response wraps the LLM result in an `orchestration_result` envelope.
"""

from typing import Any

_DEFAULT_MAX_TOKENS = 8192


class OrchestrationFamily:
    def __init__(self, model: str, max_tokens: int = _DEFAULT_MAX_TOKENS) -> None:
        self._model = model
        self._max_tokens = max_tokens

    def build_request(
        self, system: str, user: str, stream: bool
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        config: dict[str, Any] = {
            "module_configurations": {
                "templating_module_config": {
                    "template": messages,
                },
                "llm_module_config": {
                    "model_name": self._model,
                    "model_version": "latest",
                    "model_params": {"max_tokens": self._max_tokens},
                },
            },
        }
        if stream:
            config["stream"] = True
        return {
            "orchestration_config": config,
            "input_params": {},
            "messages_history": [],
        }

    def parse_response(self, response: dict[str, Any]) -> str:
        result = response.get("orchestration_result", {})
        if not isinstance(result, dict):
            return ""
        choices = result.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0]
        if not isinstance(first, dict):
            return ""
        msg = first.get("message", {})
        if not isinstance(msg, dict):
            return ""
        content = msg.get("content")
        return content if isinstance(content, str) else ""

    def parse_stream_event(self, event: dict[str, Any]) -> str | None:
        result = event.get("orchestration_result")
        if not isinstance(result, dict):
            return None
        choices = result.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        delta = first.get("delta", {})
        if not isinstance(delta, dict):
            return None
        content = delta.get("content")
        return content if isinstance(content, str) else None
