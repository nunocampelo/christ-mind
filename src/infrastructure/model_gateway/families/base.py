"""The chat family seam: one adapter per model family (Anthropic, later GPT/Gemini).

SCAFFOLD ONLY — nothing wires a chat path through the gateway yet (see the
increment plan). This exists so the future LLM-on-gateway cutover slots a family
in behind a fixed shape instead of reshaping the client. Embeddings need no such
seam; their wire shape is family-uniform.

A family owns exactly the two things that differ across model families: how a
(system, user) prompt becomes the deployment's request body, and how the
deployment's response (or a streamed event) becomes reply text. The client owns
auth and transport; the family owns shape.
"""

from typing import Any, Protocol


class ChatFamily(Protocol):
    def build_request(
        self, system: str, user: str, stream: bool
    ) -> dict[str, Any]:
        """The POST body for one chat turn, in this family's schema."""
        ...

    def parse_response(self, response: dict[str, Any]) -> str:
        """The assistant text from a non-streaming response body."""
        ...

    def parse_stream_event(self, event: dict[str, Any]) -> str | None:
        """The text delta from one streamed event, or None for events that carry
        no text (message start/stop, pings)."""
        ...
