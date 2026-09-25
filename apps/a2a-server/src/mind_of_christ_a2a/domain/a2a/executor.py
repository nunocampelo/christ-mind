"""Bridges the Mind of Christ orchestrator to the a2a-sdk server stack.

## Executor contract (a2a-sdk 1.1.2)

`execute()` MUST enqueue a `Task` object **before** any status update, or the SDK raises
`InvalidAgentResponseError: Agent should enqueue Task before TaskStatusUpdateEvent`.
`TaskUpdater.submit()` is not enough — it emits a status event, not a `Task`. Hence the
explicit `enqueue_event(Task(...))` first, then `TaskUpdater` for the transitions.

## Two typed lanes on one connection

The orchestrator's `OrchestratorEvent`s map onto the SDK's `TaskUpdater` so a client never
guesses progress from answer:

- **`StepStatusEvent` → `TaskStatusUpdateEvent`** (`working` + a message part): discrete
  milestones ("Calling find_claims"), never answer text.
- **`TokenEvent` → `TaskArtifactUpdateEvent`** on a stable `artifact_id="answer"`: first
  chunk `append=False` (creates the artifact), later chunks `append=True`. A streaming
  client keys one buffer on that id and appends.
- **`FinalEvent`** closes the artifact (`last_chunk=True`) and the terminal `complete()`
  carries the full assembled answer in `status.message`, so a blocking `SendMessage` still
  returns it there.

## The MCP subprocess is per request

Unlike the reference agent's long-lived HTTP MCP pool, our MCP client is a stdio
subprocess owned by an `async with connect()` block (`infrastructure.mcp_client`). One
`ClientSession` is a single ordered stream, not safe to share across overlapping requests,
so the subprocess is launched inside `execute()` and torn down when the request ends. The
orchestrator is built here too, per request, from that live client.

## The invariant, on the wire

The orchestrator keeps cited claims (what the Course *says*) distinct from inferred chains
(what *follows*) in `AgentAnswer`. That structured answer rides alongside the streamed
prose as a second, JSON artifact (`artifact_id="evidence"`) emitted once at the end, so the
distinction survives to the frontend rather than collapsing into the prose stream.
"""

import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, Task, TaskState, TaskStatus

from mind_of_christ_agent.application.answer import AgentRequest
from mind_of_christ_agent.application.build import build_orchestrator
from mind_of_christ_agent.domain.events import FinalEvent, StepStatusEvent, TokenEvent
from mind_of_christ_agent.infrastructure.mcp_client import connect

_ANSWER_ARTIFACT_ID = "answer"
_EVIDENCE_ARTIFACT_ID = "evidence"


class MindOfChristExecutor(AgentExecutor):
    """Runs the streaming orchestrator inside the SDK's task lifecycle, one MCP
    subprocess per request."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())
        situation = context.get_user_input()

        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.TASK_STATE_SUBMITTED),
            )
        )
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.start_work()

        buffer: list[str] = []
        answer_started = False
        try:
            async with connect() as mcp_client:
                orchestrator = build_orchestrator(mcp_client)
                request = AgentRequest(situation=situation)
                async for event in orchestrator.run_stream(request):
                    if isinstance(event, StepStatusEvent):
                        await updater.update_status(
                            TaskState.TASK_STATE_WORKING,
                            message=updater.new_agent_message(
                                parts=[Part(text=event.text)]
                            ),
                        )
                    elif isinstance(event, TokenEvent):
                        buffer.append(event.delta)
                        await updater.add_artifact(
                            parts=[Part(text=event.delta)],
                            artifact_id=_ANSWER_ARTIFACT_ID,
                            append=answer_started,
                        )
                        answer_started = True
                    elif isinstance(event, FinalEvent):
                        await updater.add_artifact(
                            parts=[Part(text="")],
                            artifact_id=_ANSWER_ARTIFACT_ID,
                            append=answer_started,
                            last_chunk=True,
                        )
                # The structured answer (cited claims kept distinct from inferred
                # chains) rides as its own artifact so the distinction survives the wire.
                if orchestrator.last_answer is not None:
                    await updater.add_artifact(
                        parts=[
                            Part(text=orchestrator.last_answer.model_dump_json())
                        ],
                        artifact_id=_EVIDENCE_ARTIFACT_ID,
                        append=False,
                        last_chunk=True,
                    )
        except Exception:
            # Any escaping exception must still emit a terminal event, or the task hangs
            # in `working` with no result. CancelledError is a BaseException, so a client
            # disconnect is NOT caught here — it propagates and the SDK cancels cleanly,
            # and `async with connect()` tears down the MCP subprocess. The static
            # message avoids leaking exception detail (which can carry the situation text
            # or an internal path).
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(text="Agent request failed")]
                )
            )
            return

        await updater.complete(
            message=updater.new_agent_message(parts=[Part(text="".join(buffer))])
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or str(uuid.uuid4())
        context_id = context.context_id or str(uuid.uuid4())
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.cancel()
