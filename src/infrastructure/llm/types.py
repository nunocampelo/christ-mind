from collections.abc import AsyncIterator, Callable

type ChatStream = Callable[[str, str], AsyncIterator[str]]
"""Sends (system prompt, user prompt) and yields the reply's text deltas."""
