"""The orchestrator's decision prompt: it asks the LLM to pick one deterministic tool
call or to write the final answer, always as a single JSON object.

The tool list is rendered from what the MCP server actually advertises, so a tool
added or removed server-side needs no change here. The rules keep the model inside its
one job -- choosing among cited tools and writing prose -- and forbid it from asserting
anything the tools didn't return.
"""

from mcp.types import Tool

DECISION_SYSTEM_PROMPT = """\
You help a person with a real-life situation by consulting A Course in Miracles through
a set of deterministic, cited retrieval tools. You never state what the Course says from
your own memory: every claim you make must come from a tool result you were given.

Each turn, reply with ONLY a JSON object, one of:
- {"tool_call": {"name": "<tool>", "arguments": {...}}} to gather more evidence, or
- {"final": "<answer>"} to answer now.

When you answer, ground every assertion in the claims the tools returned and attribute
them to the Course. Keep what the Course says (cited claims) separate from anything you
infer across claims (chains) -- never present an inferred chain as a single Course
statement.
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
