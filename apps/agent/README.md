# mind-of-christ-agent

The orchestrator: the one place an LLM interprets in the Mind of Christ system. It maps a
person's free-text situation to Course concepts, then reasons step by step — calling the
deterministic, cited MCP tools (`find_sources`, `find_claims`, `find_claims_for_entity`,
`chain_claims`) over the real stdio transport — and streams a grounded answer.

The tools stay deterministic and cited; the agent only chooses among them and writes the
closing prose. The answer keeps what the Course *says* (cited claims) distinct from what
*follows* from it (inferred chains) — never one flat list.

## Setup

From the repo root (install the shared package and mcp-server first — see the root
`CLAUDE.md`):

```sh
.venv/bin/pip install -e ".[dev]"
.venv/bin/pip install -e "apps/mcp-server[dev]"
.venv/bin/pip install -e "apps/agent[dev]"
```

## Run tests

```sh
.venv/bin/python -m pytest apps/agent/tests -q   # from the repo root
```

## Run the CLI

```sh
.venv/bin/python -m mind_of_christ_agent "I keep getting angry when criticized"
```

Needs the Anthropic proxy reachable (`ANTHROPIC_BASE_URL`, default
`http://localhost:6656`) for the mapper and the streaming answer. It launches
mind-of-christ-mcp as a subprocess for the deterministic tools — no separate server to
start. Status goes to stderr; the answer streams to stdout.

## Layout

- `domain/orchestrator.py` — the ReAct loop (`run_stream` → `OrchestratorEvent`s).
- `domain/events.py` — the internal event union (status / token / final), not wire types.
- `domain/prompt.py` — the decision prompt (pick a tool, or write the final answer).
- `infrastructure/mcp_client.py` — the stdio MCP client (launches mcp-server).
- `application/answer.py` — the request/answer DTOs (the cited-vs-inferred invariant).
- `application/build.py` — the composition root (wires mapper + MCP client + LLM stream).
- `cli.py` — `python -m mind_of_christ_agent "<situation>"`.

## Status

First backend slice. The A2A transport (`apps/a2a-server/`) and the chat frontend are the
next slices — see `.claude/plans/agent-layer-and-a2a-backend.md`.
