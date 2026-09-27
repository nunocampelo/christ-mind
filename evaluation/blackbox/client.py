"""The black-box agent client: drives the real product over its public A2A interface and
returns only externally-visible output. It imports nothing from the agent's application
internals or the MCP server -- the only shared type is `AgentAnswer`, which is itself the
public wire contract the `evidence` artifact carries. A change to tool schemas, MCP
serialization, or the artifact shape can therefore break a black-box run, which is the point.

`ask` speaks native-v1 A2A: a blocking `SendMessage` (header `A2A-Version: 1.0`) returns the
terminal task, whose `answer` artifact holds the prose and whose `evidence` artifact holds
`AgentAnswer.model_dump_json()` (answer + cited_claims kept distinct from inferred_chains).
"""

import json

import httpx
from a2a.types import Task, TaskState
from google.protobuf import json_format
from mind_of_christ_agent.application.answer import AgentAnswer

from evaluation.blackbox.evaluator import BlackBoxResponse

_EVIDENCE_ARTIFACT = "evidence"
_ANSWER_ARTIFACT = "answer"


class A2AClientError(RuntimeError):
    """The A2A call failed or returned an unusable envelope. Message is static: the raw
    envelope can carry payloads, so it is not interpolated here."""


class A2AAgentClient:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self._url = base_url.rstrip("/") + "/a2a"
        self._timeout = timeout

    def ask(self, question: str) -> BlackBoxResponse:
        task = self._send(question)
        if task.status.state != TaskState.TASK_STATE_COMPLETED:
            raise A2AClientError("agent did not complete the task")
        answer = _parse_evidence(task)
        return BlackBoxResponse(
            question=question,
            answer=answer.text,
            cited_claims=answer.cited_claims,
            inferred_chains=answer.inferred_chains,
            citation_diagnostics=answer.citation_diagnostics,
        )

    def _send(self, question: str) -> Task:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {
                "message": {
                    "messageId": "eval",
                    "role": "ROLE_USER",
                    "parts": [{"text": question}],
                }
            },
        }
        try:
            response = httpx.post(
                self._url,
                json=payload,
                headers={"A2A-Version": "1.0"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            envelope = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            raise A2AClientError("A2A request failed") from e
        if "error" in envelope:
            raise A2AClientError("A2A response carried an error")
        try:
            return json_format.ParseDict(envelope["result"]["task"], Task())
        except (KeyError, json_format.ParseError) as e:
            raise A2AClientError("A2A response was not a task") from e


def _parse_evidence(task: Task) -> AgentAnswer:
    for artifact in task.artifacts:
        if artifact.artifact_id == _EVIDENCE_ARTIFACT:
            try:
                return AgentAnswer.model_validate_json(artifact.parts[0].text)
            except (IndexError, ValueError) as e:
                raise A2AClientError("evidence artifact was unparseable") from e
    raise A2AClientError("response carried no evidence artifact")
