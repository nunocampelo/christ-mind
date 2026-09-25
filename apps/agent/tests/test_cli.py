"""CLI smoke test: with the MCP transport and orchestrator build stubbed, running the
module prints the streamed answer to stdout and status to stderr."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

import mind_of_christ_agent.cli as cli
from mind_of_christ_agent.application.answer import AgentRequest
from mind_of_christ_agent.domain.events import (
    FinalEvent,
    OrchestratorEvent,
    StepStatusEvent,
    TokenEvent,
)


class _ScriptedOrchestrator:
    def __init__(self, events: list[OrchestratorEvent]):
        self._events = events

    async def run_stream(self, request: AgentRequest) -> AsyncIterator[OrchestratorEvent]:
        for event in self._events:
            yield event


def test_cli_prints_streamed_answer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    @asynccontextmanager
    async def _fake_connect() -> AsyncIterator[object]:
        yield object()

    events: list[OrchestratorEvent] = [
        StepStatusEvent(text="Mapped situation to 1 concept(s)"),
        TokenEvent(delta="Peace "),
        TokenEvent(delta="is yours."),
        FinalEvent(text="Peace is yours."),
    ]
    monkeypatch.setattr(cli, "connect", _fake_connect)
    monkeypatch.setattr(cli, "build_orchestrator", lambda client: _ScriptedOrchestrator(events))
    monkeypatch.setattr(cli.sys, "argv", ["mind_of_christ_agent", "I am afraid"])

    cli.main()

    captured = capsys.readouterr()
    assert captured.out == "Peace is yours.\n"
    assert "Mapped situation to 1 concept(s)" in captured.err


def test_cli_rejects_empty_situation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli.sys, "argv", ["mind_of_christ_agent", "   "])
    with pytest.raises(SystemExit) as excinfo:
        cli.main()
    assert excinfo.value.code == 2
