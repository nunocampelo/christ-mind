"""The orchestrator's decision prompt: it asks the LLM to pick one deterministic tool
call or to write the final answer, always as a single JSON object.

The tool list is rendered from what the MCP server actually advertises, so a tool
added or removed server-side needs no change here. The rules keep the model inside its
one job -- choosing among cited tools and writing prose -- and forbid it from asserting
anything the tools didn't return.
"""

from mcp.types import Tool

from mind_of_christ_agent.application.answer import CitedClaim, InferredChain

DECISION_SYSTEM_PROMPT = """\
You help a person with a real-life situation by consulting A Course in Miracles through
a set of deterministic, cited retrieval tools. You never state what the Course says from
your own memory: every claim you make must come from a tool result you were given.

Each turn, reply with ONLY a JSON object, one of:
- {"tool_call": {"name": "<tool>", "arguments": {...}}} to gather more evidence, or
- {"final": "<answer>"} to answer now.

Gather evidence, then answer. A couple of tool calls is usually enough; once you have
relevant claims, emit {"final": ...} rather than searching indefinitely. Do not refine the
same query repeatedly -- if a search returns something usable, answer with it.

When you answer, ground every assertion in the claims the tools returned and attribute
them to the Course. Keep what the Course says (cited claims) separate from anything you
infer across claims (chains) -- never present an inferred chain as a single Course
statement.

When you write the final answer, write prose the person can read directly -- never expose
this decision protocol in the answer text. Ground the answer in the cited claims: you may
connect multiple claims to address the situation, but never present such a synthesis as
though it were a single statement from the Course, and do not introduce Course teachings
the cited claims don't support.
"""


ANSWER_SYSTEM_PROMPT = """\
You are writing the final answer to a person's real-life situation, grounded in
A Course in Miracles, from the cited claims already gathered by the retrieval tools.

Write prose the person can read directly -- never JSON, never a tool call, and
never expose the decision protocol.

Ground the answer in the cited claims and attribute Course teachings to the
Course. Preserve the distinction between what the cited claims explicitly say
and what can be inferred or synthesized from them. You may connect multiple
claims to address the person's situation, but never present such a synthesis
as though it were a single statement from the Course.

Do not introduce Course teachings that are not supported by the cited claims.
Do not add unsupported factual, doctrinal, or psychological claims.
"""


def _render_tools(tools: list[Tool]) -> str:
    return "\n".join(f"- {tool.name}: {tool.description or ''}".rstrip() for tool in tools)


def decision_user_prompt(
    situation: str, concepts: list[str], tools: list[Tool], observations: list[str]
) -> str:
    seen = "\n".join(observations) if observations else "(no tools called yet)"
    return (
        f"Situation:\n{situation}\n\n"
        f"Concepts mapped from it: {', '.join(concepts) or '(none)'}\n\n"
        f"Available tools:\n{_render_tools(tools)}\n\n"
        f"Observations so far:\n{seen}\n\n"
        "Decide the next step as a single JSON object."
    )


def answer_user_prompt(
    situation: str,
    cited_claims: list[CitedClaim],
    inferred_chains: list[InferredChain],
) -> str:
    cited = "\n".join(
        f"- [{c.source_id}] {c.subject} {c.verb_phrase} {c.object or ''}".rstrip()
        for c in cited_claims
    )
    chains = "\n".join(
        "- inferred: "
        + " -> ".join(f"{link.subject} {link.verb_phrase}".strip() for link in chain.links)
        for chain in inferred_chains
    )
    return (
        f"Situation:\n{situation}\n\n"
        f"Cited claims (what the Course says):\n{cited or '(none)'}\n\n"
        f"Inferred chains (connections you may draw, marked inferred):\n{chains or '(none)'}\n\n"
        "Write the answer now."
    )
