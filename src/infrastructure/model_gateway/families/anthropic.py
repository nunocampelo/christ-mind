"""The Anthropic Messages family — the first `ChatFamily` impl.

SCAFFOLD ONLY, not wired into any chat path yet (see families/base.py). Pins the
Messages request/response shape so the future gateway chat cutover has a concrete
adapter to build against.
"""

from typing import Any

_DEFAULT_MAX_TOKENS = 8192


class AnthropicFamily:
    def __init__(self, model: str, max_tokens: int = _DEFAULT_MAX_TOKENS) -> None:
        self._model = model
        self._max_tokens = max_tokens

    def build_request(self, system: str, user: str, stream: bool) -> dict[str, Any]:
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "stream": stream,
        }

    def parse_response(self, response: dict[str, Any]) -> str:
        blocks = response.get("content", [])
        if not isinstance(blocks, list):
            return ""
        return "".join(
            b.get("text", "")
            for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )

    def parse_stream_event(self, event: dict[str, Any]) -> str | None:
        if event.get("type") != "content_block_delta":
            return None
        delta = event.get("delta", {})
        if isinstance(delta, dict) and delta.get("type") == "text_delta":
            text = delta.get("text")
            return text if isinstance(text, str) else None
        return None
