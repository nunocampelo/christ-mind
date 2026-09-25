# Agent layer + A2A backend (christ-mind full-stack, backend slices)

## Context

The semantic-layer roadmap (#1–#9) is done: deterministic, cited retrieval/synthesis
exposed as MCP tools, plus a `map_situation` LLM mapper (#9). Last turn `map_situation` was
added as a 5th MCP tool; the user questioned that — an LLM tool called by an LLM agent is a
strange loop. The agreed target is a full-stack app built inside-out: **agent orchestrator →
A2A transport → full-window ChatGPT-style chat frontend**, where the agent is the one place
an LLM interprets, and the MCP tools stay deterministic and cited. This plan covers the
**backend slices buildable now, CLI-first**; the A2A server and frontend are sketched as
roadmap only (not built until the orchestration is proven from a CLI, per CLAUDE.md's "only
create an app once it has real code").

Reference: a prior production A2A agent (a2a-sdk 1.1.2, FastAPI, hexagonal). Mirror its shape;
build **native v1** (`enable_v0_3_compat=False`); the frontend is a port of a proven chat-app
PR plan. The invariant to preserve at every layer: "the Course says X" (cited
tool results) stays distinct from "this follows" (inferred chains).

## Build order (this plan details PR 1–2; PR 3–4 are roadmap)

| PR | Slice | Built now? |
| -- | ----- | ---------- |
| 1 | Revert the `map_situation` MCP tool | yes |
| 2 | `apps/agent/` orchestrator + CLI (LLM + MCP tools + mapper) | yes |
| 3 | `apps/a2a-server/` — FastAPI A2A transport over the agent | roadmap |
| 4 | Full-window ChatGPT-style chat frontend (React/Vite/Tailwind) | roadmap |

---

## PR 1 — Revert the misplaced MCP tool

Back out last turn's wrapper so the mapper isn't reachable at the wrong layer. The #9 value
(`application/mapping/`, `evaluation/mapping/`, `anthropic_proxy.make_mapper`) stays.

- `apps/mcp-server/src/mind_of_christ_mcp/server.py` — remove the `map_situation` tool, the
  lazy `_mapper`/`_situation_mapper` wiring, and the `application.mapping` + `make_mapper`
  imports.
- `apps/mcp-server/src/mind_of_christ_mcp/schemas/situations.py` — delete.
- `apps/mcp-server/tests/test_server.py` — remove the two `map_situation` tests + the
  `_StubMapper`/`stub_mapper` fixture.
- Verify: `pytest apps/mcp-server/tests` green (back to 14), `pyright` clean, 4 tools register.

## PR 2 — `apps/agent/` orchestrator + CLI (the first real slice)

A new app, mirroring `apps/mcp-server`'s layout (own `pyproject.toml`, exact pins, editable
install, `src/` layout root, empty `__init__.py`, direct imports). The agent is an MCP
**client** of mcp-server over stdio — the real transport boundary — and owns the mapper.

### Layering (inside the app's `src/mind_of_christ_agent/`)

Mirror the reference agent's hexagonal split, scaled down:

- `domain/orchestrator.py` — the ReAct loop as an async generator
  `run_stream(request) -> AsyncIterator[OrchestratorEvent]`. Steps: call `map_situation`
  (via the injected mapper) to turn the user's situation into concepts; prompt the LLM for a
  JSON decision (`{"tool_call": {...}}` or `{"final": "..."}`) listing the MCP tools; on a
  tool call, dispatch to the MCP client and feed the observation back; loop to `max_steps`;
  stream the final answer's tokens. Deterministic tool results and inferred chains are kept
  **distinct** in the accumulated answer state (the invariant).
- `domain/events.py` — the internal event union (mirrors the reference agent's a2a event DTOs):
  `StepStatusEvent(text)`, `TokenEvent(delta)`, `FinalEvent(text)`, as frozen pydantic
  models discriminated by a literal `kind`. NOT wire types — PR 3's executor maps these to
  A2A frames. (Typed, no bare dict, per CLAUDE.md.)
- `infrastructure/mcp_client.py` — launches mcp-server as a subprocess via the `mcp`
  package's `stdio_client` + `ClientSession` (already a dependency at 2.2.0), exposes
  `list_tools()` / `call_tool(name, arguments)`. This is the outermost boundary a component
  test mocks.
- `application/` — the agent's own composition: an `AgentRequest`/answer DTO and a
  `build_orchestrator(...)` that wires the mapper (`make_mapper` from
  `infrastructure.llm.anthropic_proxy`) + the MCP client + the LLM into an orchestrator. This
  is the composition root; domain takes its deps as parameters.
- `cli.py` (or `__main__.py`) — `python -m mind_of_christ_agent "<situation>"`, reads a
  situation, runs the orchestrator, prints the streamed answer. Mirrors mcp-server's `main()`.

### Shared-package change (root `src/`)

- `src/infrastructure/llm/anthropic_proxy.py` — add a streaming `chat_stream` alongside the
  existing `complete` (the orchestrator streams the final answer token-by-token). Keep the
  existing `Complete`/`make_complete`/`make_mapper` untouched. New type mirrors the reference
  agent's `chat_stream -> AsyncIterator[delta]`. Add whatever the Anthropic SDK streaming API needs;
  pin per the dependency rules.

### Answer contract (the DTO every upper layer depends on — pin it here)

The orchestrator's result must carry, separately: the **cited claims** (with `source_id`s,
straight from tool results) and any **inferred chains** (marked inferred, links stay
Course-attributed). Never a flat list. This shape becomes what PR 3's A2A artifact and PR 4's
UI render, so it is fixed in PR 2.

### Tests (`apps/agent/tests/`, component-first)

- Boot the orchestrator with the **MCP client boundary stubbed** (a fake session returning
  canned tool results) and the **mapper's `Complete` + the LLM `chat_stream` stubbed** —
  mock only the outermost boundaries, not the application layer. Assert the full sequence of
  emitted `OrchestratorEvent`s by equality (not truthiness): a situation → concepts →
  tool_call → observation → final, with cited vs. inferred kept distinct in the answer.
- A CLI smoke test: `python -m mind_of_christ_agent` with stubs wired, asserting the printed
  answer.
- Verify: `pytest apps/agent/tests` green, `pyright` clean (add `apps/agent/src` to the
  pyright `include`).

---

## PR 3 — `apps/a2a-server/` (roadmap, not built now)

FastAPI app mirroring the reference agent: `domain/a2a/executor.py` (subclasses `a2a.server...AgentExecutor`,
maps `OrchestratorEvent`s → A2A frames: `Task` enqueued first, `update_status` for progress,
`add_artifact(artifact_id="answer", append=..., last_chunk=...)` for the answer stream,
`complete(message=full answer)`, `failed()` on error), `domain/a2a/agent_card.py` (port only
`render_agent_card_v1`), `api/controllers/a2a_controller.py` (`POST /a2a` →
`JsonRpcDispatcher(handler, enable_v0_3_compat=False)`), `api/dependencies.py` (composition
root; the mock seam). `InMemoryTaskStore` on app.state. `a2a-sdk==1.1.2`, FastAPI, pinned.
Auth/secrets from the environment, fail loud at boot.

## PR 4 — Full-window chat frontend (roadmap, not built now)

Port of a proven chat-app PR plan. React + Vite + Tailwind, headless
components, own design tokens. **Full-window ChatGPT-style** (the app IS the chat, root
route, centered conversation column, sticky composer, full landing empty state) — not the
reference plan's embedded side panel. Keep unchanged: `agentApi.ts` + `useA2AChat.ts`, `@a2a-js/sdk` transport,
`react-markdown`+`remark-gfm`, `streamFn` seam, streaming/typewriter, `contextId` persistence.
**Single conversation first**; the multi-conversation sidebar (and its backend list/persist
API) is a later slice. Detailed vertical-slice breakdown (React/Vite/Tailwind/shadcn, PR 1–7)
in `frontend-chat.md`.

## Not in these slices

- Multi-conversation history / sidebar + its backend persistence (later).
- Auth/identity forwarding hardening — lands with PR 3 when a real transport carries a token.
- Stop/reconnect/scroll-anchoring frontend polish (later frontend slices, per the reference plan).
- Any change to the deterministic MCP tools or `application/mapping`/`evaluation/mapping`.

## Verification (PR 1–2)

```bash
.venv/bin/python -m pytest tests apps/mcp-server/tests apps/agent/tests -q
.venv/bin/pyright
# CLI slice, stubs off — real proxy + real mcp-server subprocess:
.venv/bin/python -m mind_of_christ_agent "I keep getting angry when criticized"
```

Expect: mcp-server back to 4 tools; the agent maps the situation to concepts, calls the
deterministic tools over stdio, and streams an answer that keeps cited claims separate from
inferred chains. Git commits left to the user (no self-commit).
