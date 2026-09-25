"""The ReAct loop: the one place an LLM interprets in this system.

`run_stream` maps a free-text situation to Course concepts (via the injected mapper),
then lets the LLM decide, step by step, which deterministic MCP tool to call next --
feeding each cited observation back -- until it emits a final answer, which streams
token by token. The tools stay deterministic and cited; the model only chooses among
them and writes the closing prose.

The invariant is enforced in the accumulated answer state: `find_claims`/
`find_claims_for_entity`/`find_sources` results land in `cited_claims`; `chain_claims`
results land in `inferred_chains`. They are never merged. The final answer text is the
model's, but the structured evidence beneath it keeps "the Course says X" separate from
"this follows from what it says".
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from application.mapping.map_situation import SituationMapper, map_situation
from infrastructure.llm.anthropic_proxy import ChatStream
from mcp.types import CallToolResult, TextContent, Tool

from mind_of_christ_agent.application.answer import (
    AgentAnswer,
    AgentRequest,
    CitedClaim,
    InferredChain,
)
from mind_of_christ_agent.domain.events import (
    FinalEvent,
    OrchestratorEvent,
    StepStatusEvent,
    TokenEvent,
)
from mind_of_christ_agent.domain.prompt import DECISION_SYSTEM_PROMPT, decision_user_prompt

_CITED_TOOLS = frozenset({"find_claims", "find_claims_for_entity", "find_sources"})


class ToolClient(Protocol):
    """The MCP transport boundary the orchestrator drives -- the seam a component test
    fakes. `infrastructure.mcp_client.McpClient` is the production implementation."""

    async def list_tools(self) -> list[Tool]: ...
    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> CallToolResult: ...


class Orchestrator:
    def __init__(
        self,
        mapper: SituationMapper,
        mcp_client: ToolClient,
        chat_stream: ChatStream,
    ):
        self._mapper = mapper
        self._mcp_client = mcp_client
        self._chat_stream = chat_stream
        self.last_answer: AgentAnswer | None = None

    async def run_stream(
        self, request: AgentRequest
    ) -> AsyncIterator[OrchestratorEvent]:
        concepts = await asyncio.to_thread(
            map_situation, self._mapper, request.situation
        )
        yield StepStatusEvent(text=f"Mapped situation to {len(concepts)} concept(s)")

        tools = await self._mcp_client.list_tools()
        observations: list[str] = []
        cited_claims: list[CitedClaim] = []
        inferred_chains: list[InferredChain] = []

        for _ in range(request.max_steps):
            decision_text = await self._decide(
                request.situation, concepts, tools, observations
            )
            decision = _parse_decision(decision_text)

            tool_call = decision.get("tool_call")
            if isinstance(tool_call, dict):
                name = str(tool_call.get("name", ""))
                arguments = tool_call.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                yield StepStatusEvent(text=f"Calling {name}")
                result = await self._mcp_client.call_tool(name, arguments)
                _absorb(name, result, cited_claims, inferred_chains)
                observations.append(
                    f"Tool '{name}' returned: {_result_text(result)[:3000]}"
                )
                yield StepStatusEvent(text=f"{name} returned")
                continue

            final = decision.get("final")
            if isinstance(final, str):
                async for event in self._stream_answer(
                    final, concepts, cited_claims, inferred_chains
                ):
                    yield event
                return

        # Loop exhausted max_steps without a final decision: answer from whatever was
        # gathered rather than leaving the user with nothing.
        async for event in self._stream_answer(
            "", concepts, cited_claims, inferred_chains
        ):
            yield event

    async def _decide(
        self,
        situation: str,
        concepts: list[str],
        tools: list[Tool],
        observations: list[str],
    ) -> str:
        user = decision_user_prompt(situation, concepts, tools, observations)
        chunks: list[str] = []
        async for delta in self._chat_stream(DECISION_SYSTEM_PROMPT, user):
            chunks.append(delta)
        return "".join(chunks)

    async def _stream_answer(
        self,
        final_hint: str,
        concepts: list[str],
        cited_claims: list[CitedClaim],
        inferred_chains: list[InferredChain],
    ) -> AsyncIterator[OrchestratorEvent]:
        text_parts: list[str] = []
        async for delta in self._chat_stream(
            DECISION_SYSTEM_PROMPT, _answer_user_prompt(final_hint, cited_claims)
        ):
            text_parts.append(delta)
            yield TokenEvent(delta=delta)
        text = "".join(text_parts)
        # The structured answer travels alongside the streamed prose; a later slice's
        # A2A artifact carries it, keeping cited claims distinct from inferred chains.
        # The FinalEvent's text is the whole prose.
        self.last_answer = AgentAnswer(
            text=text,
            concepts=concepts,
            cited_claims=cited_claims,
            inferred_chains=inferred_chains,
        )
        yield FinalEvent(text=text)


def _answer_user_prompt(final_hint: str, cited_claims: list[CitedClaim]) -> str:
    citations = "\n".join(
        f"- [{c.source_id}] {c.subject} {c.verb_phrase} {c.object or ''}".rstrip()
        for c in cited_claims
    )
    return (
        "Write the answer to the person's situation. Ground every assertion in the "
        "cited claims below and attribute them to the Course. Keep what the Course "
        "says separate from anything you infer.\n\n"
        f"Draft: {final_hint}\n\nCited claims:\n{citations or '(none)'}"
    )


def _parse_decision(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```").removeprefix("json").strip()
        stripped = stripped.removesuffix("```").strip()
    try:
        parsed = json.loads(stripped)
    except ValueError:
        return {"final": text}
    if not isinstance(parsed, dict):
        return {"final": text}
    return parsed


def _absorb(
    name: str,
    result: CallToolResult,
    cited_claims: list[CitedClaim],
    inferred_chains: list[InferredChain],
) -> None:
    payload = result.structured_content
    if not isinstance(payload, dict):
        return
    if name in _CITED_TOOLS:
        for item in payload.get("result", []):
            claim = _to_cited_claim(item)
            if claim is not None:
                cited_claims.append(claim)
    elif name == "chain_claims":
        for chain in payload.get("chains", []):
            if not isinstance(chain, dict):
                continue
            links = [
                claim
                for link in chain.get("links", [])
                if (claim := _to_cited_claim(link)) is not None
            ]
            inferred_chains.append(InferredChain(links=links))


def _to_cited_claim(item: object) -> CitedClaim | None:
    if not isinstance(item, dict) or "claim_id" not in item:
        return None
    return CitedClaim(
        claim_id=str(item["claim_id"]),
        source_id=str(item.get("source_id", "")),
        subject=str(item.get("subject", "")),
        predicate=str(item.get("predicate", "")),
        object=item.get("object"),
        verb_phrase=str(item.get("verb_phrase", "")),
        evidence=str(item.get("evidence", "")),
    )


def _result_text(result: CallToolResult) -> str:
    return "".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )
