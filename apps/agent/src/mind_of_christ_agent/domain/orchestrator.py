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
import re
from collections.abc import AsyncIterator
from typing import Any, Protocol

from application.mapping.map_situation import SituationMapper, map_situation
from infrastructure.llm.anthropic_proxy import ChatStream
from mcp.types import CallToolResult, TextContent, Tool

from mind_of_christ_agent.application.answer import (
    AgentAnswer,
    AgentRequest,
    CitationDiagnostics,
    CitedClaim,
    InferredChain,
)
from mind_of_christ_agent.domain.events import (
    FinalEvent,
    OrchestratorEvent,
    StepStatusEvent,
    TokenEvent,
)
from mind_of_christ_agent.domain.citations import extract_markers
from mind_of_christ_agent.domain.final_stream import FinalValueExtractor
from mind_of_christ_agent.domain.prompt import (
    ANSWER_SYSTEM_PROMPT,
    DECISION_SYSTEM_PROMPT,
    answer_user_prompt,
    decision_user_prompt,
)

_CITED_TOOLS = frozenset({"find_claims", "find_claims_for_entity", "find_sources"})

# Tools that *retrieve* by a search term, so a repeat for an already-searched term is
# redundant. Currently identical to _CITED_TOOLS, but kept separate on purpose: the
# repeat-search guard is about retrieval, not about whether a result is cited, and a future
# retrieval tool whose output isn't a cited claim would still belong here. chain_claims is
# deliberately absent -- it walks edges from an already-retrieved subject (see the guard).
_RETRIEVAL_TOOLS = frozenset({"find_claims", "find_claims_for_entity", "find_sources"})


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

        # Every normalized search term already looked for this turn, across any tool. The
        # model is prone to chasing a zero-result target with reworded terms and different
        # tools ("the mind of Christ" -> "Christ's mind" -> find_sources -> for_entity); a
        # call whose terms are all already covered is answered from this set instead of
        # re-run, which is what actually breaks the loop (the prompt rule alone doesn't hold).
        searched_terms: set[str] = set()

        # The concepts to search are already known from the mapping, so retrieve them in
        # one deterministic batch rather than spending an LLM decision call per concept.
        # The model still gets `find_claims` for reactive follow-up when this is thin.
        if concepts:
            yield StepStatusEvent(
                text=f"Calling find_claims for {len(concepts)} mapped concept(s)"
            )
            searched_terms.update(_call_terms({"queries": concepts}))
            result = await self._mcp_client.call_tool(
                "find_claims", {"queries": concepts}
            )
            _absorb("find_claims", result, cited_claims, inferred_chains)
            observations.append(
                f"Tool 'find_claims' returned: {_result_text(result)[:3000]}"
            )
            yield StepStatusEvent(
                text=f"find_claims returned {_result_summary('find_claims', result)}"
            )

        for _ in range(request.max_steps):
            # One streaming decision call. The extractor reveals a `final` string's
            # tokens live (nothing for a `tool_call`); the raw text is parsed after the
            # stream ends to route the decision.
            answer_parts: list[str] = []
            extractor = FinalValueExtractor()
            chunks: list[str] = []
            async for delta in self._chat_stream(
                DECISION_SYSTEM_PROMPT,
                decision_user_prompt(
                    request.situation, concepts, tools, observations
                ),
            ):
                chunks.append(delta)
                revealed = extractor.feed(delta)
                if revealed:
                    answer_parts.append(revealed)
                    yield TokenEvent(delta=revealed)
            decision = _parse_decision("".join(chunks))

            tool_call = decision.get("tool_call")
            if isinstance(tool_call, dict):
                name = str(tool_call.get("name", ""))
                arguments = tool_call.get("arguments")
                if not isinstance(arguments, dict):
                    arguments = {}
                # The guard is about redundant *retrieval*. chain_claims is synthesis -- it
                # walks edges from an already-retrieved subject, so operating on a term
                # that's been searched is its normal use, not a repeat.
                terms = _call_terms(arguments) if name in _RETRIEVAL_TOOLS else frozenset()
                if terms and terms <= searched_terms:
                    # Every term this retrieval looks for has already been searched this
                    # turn (under any wording or tool). Don't re-run it; tell the model so
                    # it stops chasing the same target and answers.
                    observations.append(
                        f"Tool '{name}' looks for terms already searched this turn with no "
                        "new results -- do not search them again; answer with what you have."
                    )
                    yield StepStatusEvent(text=f"Skipped repeat search via {name}")
                    continue
                searched_terms.update(terms)
                yield StepStatusEvent(text=f"Calling {name}{_arg_summary(arguments)}")
                result = await self._mcp_client.call_tool(name, arguments)
                _absorb(name, result, cited_claims, inferred_chains)
                observations.append(
                    f"Tool '{name}' returned: {_result_text(result)[:3000]}"
                )
                yield StepStatusEvent(
                    text=f"{name} returned {_result_summary(name, result)}"
                )
                continue

            final = decision.get("final")
            if isinstance(final, str):
                # The `final` tokens already streamed via the extractor; the parsed value
                # is the authoritative text (it also covers any tail the extractor's
                # buffering hadn't flushed). Close with it and the structured answer.
                yield self._final_event(
                    final, concepts, cited_claims, inferred_chains
                )
                return

        # Loop exhausted max_steps without the model ever emitting {"final"} (it kept
        # searching). Force one answer-only call over what was gathered, so the user always
        # gets prose rather than an empty reply.
        text_parts: list[str] = []
        async for delta in self._chat_stream(
            ANSWER_SYSTEM_PROMPT,
            answer_user_prompt(request.situation, cited_claims, inferred_chains),
        ):
            text_parts.append(delta)
            yield TokenEvent(delta=delta)
        yield self._final_event(
            "".join(text_parts), concepts, cited_claims, inferred_chains
        )

    def _final_event(
        self,
        text: str,
        concepts: list[str],
        cited_claims: list[CitedClaim],
        inferred_chains: list[InferredChain],
    ) -> OrchestratorEvent:
        # The structured answer travels alongside the streamed prose; the A2A artifact
        # carries it, keeping cited claims distinct from inferred chains. The FinalEvent's
        # text is the whole prose.
        self.last_answer = AgentAnswer(
            text=text,
            concepts=concepts,
            cited_claims=cited_claims,
            inferred_chains=inferred_chains,
            citation_diagnostics=_diagnose_citations(text, cited_claims),
        )
        return FinalEvent(text=text)


def _diagnose_citations(
    text: str, cited_claims: list[CitedClaim]
) -> CitationDiagnostics:
    """Soft audit: markers the prose cites vs. claims actually gathered. Never rejects --
    the prose has already streamed. Inferred-chain links are not part of `cited_claims`, so
    they are intentionally not counted as citable here; the prose cites Course claims."""
    marked = set(extract_markers(text))
    gathered = {c.claim_id for c in cited_claims}
    return CitationDiagnostics(
        unknown_ids=sorted(marked - gathered),
        unused_claim_ids=sorted(gathered - marked),
    )


def _parse_decision(text: str) -> dict[str, object]:
    """Pull the decision object out of the model's reply.

    The reply is meant to be a bare `{"tool_call": ...}` / `{"final": ...}` object, but a
    model may wrap it in a ```json fence or emit reasoning prose around it. We try the whole
    (fence-stripped) text, then scan for a balanced `{...}` object -- preferring one that
    carries `"tool_call"` so reasoning-then-tool_call resolves to the tool, not the prose.
    A reply with no JSON object at all yields an empty decision rather than leaking the raw
    protocol text into the answer stream.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```").removeprefix("json").strip()
        stripped = stripped.removesuffix("```").strip()

    whole = _try_object(stripped)
    if whole is not None:
        return whole

    if '"tool_call"' in stripped:
        idx = stripped.find('"tool_call"')
        brace_start = stripped.rfind("{", 0, idx)
        if brace_start != -1:
            candidate = _scan_first_object(stripped[brace_start:])
            if candidate is not None and "tool_call" in candidate:
                return candidate

    return _scan_first_object(stripped) or {}


def _try_object(s: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(s)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _scan_first_object(s: str) -> dict[str, object] | None:
    """Return the first balanced, JSON-parseable `{...}` object in `s`, or None."""
    search_from = 0
    while True:
        start = s.find("{", search_from)
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    obj = _try_object(s[start : i + 1])
                    if obj is not None:
                        return obj
                    search_from = i + 1
                    break
        else:
            return None


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
        polarity=str(item.get("polarity", "")),
        evidence=str(item.get("evidence", "")),
    )


def _result_text(result: CallToolResult) -> str:
    return "".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


# The one argument worth showing in the trace per tool -- the query/mention/subject that
# names what the call is looking for. Anything else (limits) is noise in a status line.
_ARG_KEYS = ("queries", "query", "mention", "subject_mention")


def _arg_summary(arguments: dict[str, Any]) -> str:
    for key in _ARG_KEYS:
        value = arguments.get(key)
        if isinstance(value, list):
            shown = ", ".join(str(v) for v in value)
            return f" for {shown}" if shown else ""
        if isinstance(value, str) and value:
            return f' for "{value}"'
    return ""


_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+")


def _normalize_term(term: str) -> str:
    """Fold a search term to its core so reworded retries collide: lowercased, leading
    article dropped, possessive 's stripped, whitespace collapsed. "the Mind of God",
    "Mind of God", and "God's mind" all reduce toward the same core."""
    t = " ".join(term.lower().split())
    t = _LEADING_ARTICLE.sub("", t)
    return t.replace("'s ", " ").replace("' ", " ").strip()


def _call_terms(arguments: dict[str, Any]) -> frozenset[str]:
    """The normalized search terms a call is looking for, order-independent, so a repeat is
    recognized regardless of key order or how the terms are reworded/reordered."""
    terms: set[str] = set()
    for key in _ARG_KEYS:
        value = arguments.get(key)
        if isinstance(value, list):
            terms.update(_normalize_term(str(v)) for v in value)
        elif isinstance(value, str) and value:
            terms.add(_normalize_term(value))
    return frozenset(t for t in terms if t)


def _result_summary(name: str, result: CallToolResult) -> str:
    """A short count for the trace: how many claims (or chains) a tool call yielded, so the
    reasoning timeline reads 'find_claims returned 8 claims' rather than a bare 'returned'."""
    payload = result.structured_content
    if not isinstance(payload, dict):
        return ""
    if name == "chain_claims":
        chains = payload.get("chains")
        n = len(chains) if isinstance(chains, list) else 0
        return f"{n} chain(s)"
    items = payload.get("result")
    n = len(items) if isinstance(items, list) else 0
    return f"{n} claim(s)"
