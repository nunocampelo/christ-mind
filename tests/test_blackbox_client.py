"""Offline tests for the A2A black-box client: response parsing against the real proto
`Task` shape, with no socket. The live over-the-wire path is exercised by `--live`, not here.
"""

import pytest
from a2a.types import Artifact, Part, Task, TaskState
from mind_of_christ_agent.application.answer import AgentAnswer, CitedClaim

from evaluation.blackbox.client import A2AClientError, _parse_evidence

_CLAIM = CitedClaim(
    claim_id="632a5b31428b0a68",
    source_id="t2-0-16",
    subject="miracles",
    predicate="other",
    object="order of difficulty",
    verb_phrase="have no",
    polarity="negated",
    evidence="there is NO order of difficulty in miracles",
)
_ANSWER = AgentAnswer(
    text="No order of difficulty. [632a5b31428b0a68]",
    concepts=["miracles"],
    cited_claims=[_CLAIM],
    inferred_chains=[],
)


def _task_with_evidence(answer: AgentAnswer) -> Task:
    task = Task()
    task.status.state = TaskState.TASK_STATE_COMPLETED
    artifact = Artifact(
        artifact_id="evidence",
        parts=[Part(text=answer.model_dump_json())],
    )
    task.artifacts.append(artifact)
    return task


def test_parses_evidence_artifact_round_trip():
    parsed = _parse_evidence(_task_with_evidence(_ANSWER))
    assert parsed == _ANSWER
    assert [c.claim_id for c in parsed.cited_claims] == ["632a5b31428b0a68"]


def test_missing_evidence_artifact_raises():
    task = Task()
    task.status.state = TaskState.TASK_STATE_COMPLETED
    task.artifacts.append(Artifact(artifact_id="answer", parts=[Part(text="prose")]))
    with pytest.raises(A2AClientError):
        _parse_evidence(task)


def test_unparseable_evidence_raises():
    task = Task()
    task.artifacts.append(
        Artifact(artifact_id="evidence", parts=[Part(text="not json")])
    )
    with pytest.raises(A2AClientError):
        _parse_evidence(task)
