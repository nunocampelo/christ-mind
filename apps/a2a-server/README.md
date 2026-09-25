# mind-of-christ-a2a

The A2A transport over the orchestrator agent. A thin FastAPI app that exposes
`mind-of-christ-agent` over the A2A protocol (JSON-RPC, **native v1**), so a chat frontend
can reach the agent over HTTP. It contains no reasoning — the executor maps the
orchestrator's `OrchestratorEvent`s onto A2A frames and back, and that is all.

The agent is imported library code; the deterministic MCP tools are launched by the agent
as a stdio subprocess per request. **There is only one process to start: this server.**

## Setup

From the repo root (install the shared package, mcp-server, and agent first — see the root
`CLAUDE.md`):

```sh
.venv/bin/pip install -e ".[dev]"
.venv/bin/pip install -e "apps/mcp-server[dev]"
.venv/bin/pip install -e "apps/agent[dev]"
.venv/bin/pip install -e "apps/a2a-server[dev]"
```

## Run tests

```sh
.venv/bin/python -m pytest apps/a2a-server/tests -q   # from the repo root
```

## Run the server

```sh
AGENT_PUBLIC_URL=http://127.0.0.1:8000 .venv/bin/python -m mind_of_christ_a2a.main
```

- `AGENT_PUBLIC_URL` (**required**, fails loud at boot) — the base URL clients reach; the
  agent card advertises `<AGENT_PUBLIC_URL>/a2a` as the endpoint.
- `HOST` (default `127.0.0.1`), `PORT` (default `8000`).

Needs the Anthropic proxy reachable (the agent's mapper + streaming answer) and the
`mind_of_christ_mcp` server importable (the agent launches it as a subprocess). No separate
MCP server to start.

### Endpoints

- `POST /a2a` — the JSON-RPC endpoint. Native v1: methods are `SendMessage`, `GetTask`
  (PascalCase, proto-JSON bodies). **Clients must send the `A2A-Version: 1.0` header** — the
  SDK assumes `0.3` when it is absent and rejects the call with `-32009`.
- `GET /.well-known/agent-card.json` — the v1 agent card.

A blocking `SendMessage` returns the terminal `Task` with the full answer in
`status.message`, an `answer` artifact carrying the streamed prose, and an `evidence`
artifact carrying the structured `AgentAnswer` JSON — cited claims kept distinct from
inferred chains.

## Layout

- `domain/a2a/executor.py` — maps `OrchestratorEvent`s → A2A frames; owns the per-request
  MCP subprocess (`async with connect()`) and builds the orchestrator from it.
- `domain/a2a/agent_card.py` — the v1 agent card, validated against the SDK proto.
- `api/controllers/a2a_controller.py` — `POST /a2a` → the SDK `JsonRpcDispatcher`.
- `api/controllers/agent_card_controller.py` — the well-known card route.
- `api/dependencies.py` — composition root; `get_a2a_dispatcher` is the test seam.
- `main.py` — the FastAPI app, lifespan (proto card + task store on `app.state`), and the
  `mind-of-christ-a2a` entrypoint.

## Status

Second backend slice (PR 3). The chat frontend (PR 4) is next — see
`.claude/plans/agent-layer-and-a2a-backend.md` and `.claude/plans/frontend-chat.md`. The
frontend must send `A2A-Version: 1.0` on every `/a2a` call.
