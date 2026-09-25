"""A `Complete` backed by the Anthropic proxy that Claude Code itself talks to.

The proxy speaks the Anthropic Messages API on `ANTHROPIC_BASE_URL` (default
`http://localhost:6656`) and holds the real credentials, so the SDK's own
`api_key` is a placeholder it never validates. The model is named in the proxy's
own scheme (`anthropic--claude-4.8-opus`), not the public one.
"""

import os

from anthropic import Anthropic, AnthropicError

from application.extraction.prompt import Complete, PromptedClaimExtractor
from application.mapping.prompt import PromptedSituationMapper
from application.resolution.prompt import PromptedResolver

_DEFAULT_BASE_URL = "http://localhost:6656"
_DEFAULT_MODEL = "anthropic--claude-4.8-opus"
_MAX_TOKENS = 8192


class AnthropicProxyError(Exception):
    """The proxy call failed. Chained from the SDK error so the original
    traceback still prints, but its message isn't interpolated here: it can
    carry the request payload or an internal URL.
    """


def _client() -> Anthropic:
    return Anthropic(
        base_url=os.environ.get("ANTHROPIC_BASE_URL", _DEFAULT_BASE_URL),
        api_key="unused-local-proxy",
    )


def make_complete(model: str | None = None) -> Complete:
    client = _client()
    model = model or os.environ.get("ANTHROPIC_EXTRACTION_MODEL", _DEFAULT_MODEL)

    def complete(system: str, user: str) -> str:
        try:
            message = client.messages.create(
                model=model,
                max_tokens=_MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except AnthropicError as e:
            raise AnthropicProxyError("Anthropic proxy request failed") from e
        return "".join(
            block.text for block in message.content if block.type == "text"
        )

    return complete


def make_extractor() -> PromptedClaimExtractor:
    return PromptedClaimExtractor(make_complete())


def make_resolver() -> PromptedResolver:
    return PromptedResolver(make_complete())


def make_mapper() -> PromptedSituationMapper:
    return PromptedSituationMapper(make_complete())
