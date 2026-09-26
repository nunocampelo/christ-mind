"""End-to-end through the real FastAPI + a2a-sdk stack, with only the outermost
boundaries stubbed (the MCP subprocess and the orchestrator build). A blocking native-v1
`SendMessage` must return the terminal task with the full answer, the streamed answer
artifact, and a distinct evidence artifact.

Native v1 keys the wire version off the `A2A-Version` header; absent, the SDK assumes 0.3
and rejects. The header is `1.0` here -- the same one PR 4's frontend must send.
"""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import Task, TaskState
from fastapi.testclient import TestClient
from google.protobuf import json_format

import mind_of_christ_a2a.domain.a2a.executor as executor_module
import mind_of_christ_a2a.main as main_module
from mind_of_christ_a2a.main import app
from mind_of_christ_agent.application.answer import (
    AgentAnswer,
    CitedClaim,
    InferredChain,
)
from mind_of_christ_agent.domain.events import FinalEvent, StepStatusEvent, TokenEvent

_CLAIM = CitedClaim(
    claim_id="c1",
    source_id="s1",
    subject="the ego",
    predicate="teaches",
    object="attack",
    verb_phrase="teaches",
    polarity="affirmed",
    evidence="The ego teaches attack.",
)
_ANSWER = AgentAnswer(
    text="Forgiveness undoes it.",
    concepts=["forgiveness"],
    cited_claims=[_CLAIM],
    inferred_chains=[InferredChain(links=[_CLAIM])],
)


class _StubOrchestrator:
    last_answer = _ANSWER

    async def run_stream(self, _request: object) -> AsyncIterator[object]:
        yield StepStatusEvent(text="Calling find_claims")
        yield TokenEvent(delta="Forgiveness ")
        yield TokenEvent(delta="undoes it.")
        yield FinalEvent(text="Forgiveness undoes it.")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    @asynccontextmanager
    async def fake_connect() -> AsyncIterator[object]:
        yield object()

    async def in_memory_store() -> tuple[InMemoryTaskStore, None]:
        return InMemoryTaskStore(), None

    monkeypatch.setenv("AGENT_PUBLIC_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(executor_module, "connect", fake_connect)
    monkeypatch.setattr(
        executor_module, "build_orchestrator", lambda _mcp: _StubOrchestrator()
    )
    monkeypatch.setattr(main_module, "build_task_store", in_memory_store)
    with TestClient(app) as c:
        yield c


def _send(client: TestClient, situation: str) -> Task:
    """Send a blocking native-v1 SendMessage and parse the terminal task into the SDK's
    typed `Task` proto, so assertions use typed field access rather than dict indexing."""
    params = {
        "message": {
            "messageId": "m1",
            "role": "ROLE_USER",
            "parts": [{"text": situation}],
        }
    }
    response = client.post(
        "/a2a",
        json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": params},
        headers={"A2A-Version": "1.0"},
    )
    assert response.status_code == 200
    envelope = response.json()
    assert "error" not in envelope, envelope
    return json_format.ParseDict(envelope["result"]["task"], Task())


def test_agent_card_served_at_well_known(client: TestClient) -> None:
    body = client.get("/.well-known/agent-card.json").json()
    assert body["name"] == "Mind of Christ Agent"
    assert body["supportedInterfaces"][0]["url"] == "http://127.0.0.1:8000/a2a"


def test_send_message_returns_answer_and_distinct_evidence(client: TestClient) -> None:
    task = _send(client, "I can't forgive someone")

    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    answer_text = "".join(p.text for p in task.status.message.parts)
    assert answer_text == "Forgiveness undoes it."

    artifacts = {a.artifact_id: a for a in task.artifacts}
    streamed = "".join(p.text for p in artifacts["answer"].parts)
    assert streamed == "Forgiveness undoes it."

    evidence = json.loads(artifacts["evidence"].parts[0].text)
    assert AgentAnswer.model_validate(evidence) == _ANSWER


def test_missing_version_header_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "m1",
                    "role": "ROLE_USER",
                    "parts": [{"text": "x"}],
                }
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32009
