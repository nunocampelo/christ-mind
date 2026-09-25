"""CLI entry point: run the orchestrator over one situation and print the answer.

    python -m mind_of_christ_agent "I keep getting angry when criticized"

Status events go to stderr (progress), the answer tokens stream to stdout, so piping
stdout captures just the answer. This drives the whole backend over the real MCP stdio
transport -- the first proof the orchestration works end to end before an A2A server or
UI is built.
"""

import asyncio
import sys

from mind_of_christ_agent.application.answer import AgentRequest
from mind_of_christ_agent.application.build import build_orchestrator
from mind_of_christ_agent.domain.events import FinalEvent, StepStatusEvent, TokenEvent
from mind_of_christ_agent.infrastructure.mcp_client import connect


async def _run(situation: str) -> None:
    async with connect() as mcp_client:
        orchestrator = build_orchestrator(mcp_client)
        async for event in orchestrator.run_stream(AgentRequest(situation=situation)):
            if isinstance(event, StepStatusEvent):
                print(f"[{event.text}]", file=sys.stderr, flush=True)
            elif isinstance(event, TokenEvent):
                print(event.delta, end="", flush=True)
            elif isinstance(event, FinalEvent):
                print(flush=True)


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('usage: python -m mind_of_christ_agent "<situation>"', file=sys.stderr)
        raise SystemExit(2)
    asyncio.run(_run(sys.argv[1]))


if __name__ == "__main__":
    main()
