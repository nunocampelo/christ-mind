# Durable conversation history (ConversationRepository) + ChatGPT-style sidebar

> **STATUS: COMPLETE (2026-09-26).** All five slices A–E implemented and committed. Full
> stack: durable Postgres task store + Alembic; `ConversationRepository` over own tables with
> `content`/`message_json` split; REST read surface (`GET /conversations`, `/conversations/{id}`);
> `react-router-dom` sidebar with URL routing (`/`, `/c/:conversationId`), new-chat/switch;
> rename (`PATCH`) + delete (`DELETE`, idempotent). Per-slice plan files (harness):
> `pr-b-conversation-repository.md`, `pr-c-conversation-read-path.md`,
> `pr-d-conversation-sidebar.md`, `pr-e-rename-delete.md` (PR A folded into the "added alembic"
> commit). One deferred item: deleting a conversation does NOT prune its `a2a_tasks` rows
> (harmless orphans). Deferred UX: collapsible sidebar (built fixed for now).

## Context

The frontend chat port (PR 1–7) is complete but single-conversation: identity is one
server-assigned `contextId` in `sessionStorage`, and all history (`turns`, `lastTaskId`)
is client-held and memory-only, lost on reload. The deferred next slice is a ChatGPT-style
sidebar (new chat / switch / rename / delete), which needs durable, server-owned history.

**Chosen architecture (decided with the user):** conversation history is a **first-class
persisted model** — a dedicated `ConversationRepository` over its own `conversations` +
`conversation_messages` tables — **not** reconstructed from A2A Tasks. Rationale: A2A Tasks
represent *executions/results*; conversation messages represent *conversation history*.
Deriving history from the Task shape couples the conversational model to the A2A task
lifecycle. Instead, the repository and the A2A `DatabaseTaskStore` **share one
`AsyncEngine`**, and `contextId` is translated to `conversation_id` at the A2A boundary.

This adapts the gcm "Story 2" conversation-repository spec to christ-mind: we carry the
architecture, and drop the gcm-only machinery that doesn't exist here (`MemoryStore`,
`SessionMemory`, `/chat`, `/session`, `sessionId`, `/assistant`, `/report`,
`AGENT_ENABLE_MEMORY`, `AGENT_MEMORY_STORAGE_DIR`, `run_in_threadpool`, HANA).

**Locked decisions:**
- DB: **Postgres everywhere** (local via docker-compose, same in prod), `asyncpg`, one
  driver stack, pgvector-ready for the corpus. No SQLite hedge.
- Migrations: **Alembic owns all DDL** — hand-written migrations, `create_table=False` on
  the task store. Not the SDK's `create_all`, not `create_all` at startup.
- Titles: derived from the first user message (no LLM titling), stored as
  `conversations.summary` / overridable.

## Naming & the one-id-three-names seam

`contextId` stays an A2A concept; internally the app calls it `conversation_id`. On the
wire christ-mind has only the A2A boundary today (no `/chat` REST), so translation is one
line in the A2A executor: `conversation_id = context.context_id`. DTO vs ORM are kept
distinct — `Conversation` / `ConversationMessage` DTOs (frozen pydantic) vs
`ConversationRow` / `ConversationMessageRow` ORM (`Row` suffix separates them across
layers).

## Cross-cutting DB decision

One shared async-SQLAlchemy engine, one `DATABASE_URL` (fail-loud if unset at lifespan,
before uvicorn accepts traffic — mirroring `_agent_public_url()`). Two logical stores on
the one engine: the SDK owns the `a2a_tasks` table; the `ConversationRepository` owns
`conversations` + `conversation_messages`. The corpus (Sources/Claims out of the in-memory
`list_sources()` stub) later gets its own tables on the same engine. Postgres +
`asyncpg`; pgvector when corpus embeddings arrive.

## Schema (owned by Alembic)

- `conversations(conversation_id PK, summary, created_at, updated_at)`
- `conversation_messages(id PK, conversation_id FK→conversations ON DELETE CASCADE, role,
  content, ts, seq)`, index on `(conversation_id, seq)`.
- `seq` = per-conversation append counter for stable read order independent of `ts`.
  **Concurrency:** `append_message(conversation_id, role, content)` allocates `seq` and
  inserts **in one transaction**, with a `UNIQUE(conversation_id, seq)` constraint so two
  simultaneous appends can't collide silently — a loser retries rather than duplicating a
  seq. `summarize_if_needed` trims the tail and updates `summary` in a single transaction;
  a concurrent reader sees pre- or post-trim state, never a torn read.
- `a2a_tasks` (a2a-sdk `TaskMixin` shape, hand-written): columns `id`, `context_id`,
  `kind`, `owner`, `last_updated`, `status`(JSON), `artifacts`(JSON), `history`(JSON),
  `protocol_version`, `metadata`(JSON — literally named `metadata`, the SDK's
  `task_metadata` attr maps to `name='metadata'`); indexes `ix_a2a_tasks_id` and
  `idx_a2a_tasks_owner_last_updated`. Verified against `a2a.server.models.TaskMixin`
  (a2a-sdk 1.1.2). Generate once via `create_task_model("a2a_tasks")` + `Base.metadata`
  autogenerate, review, then freeze as a hand-written migration.

## SDK facts verified

- `DatabaseTaskStore(engine, table_name=..., create_table=False, owner_resolver=resolve_user_scope)`
  takes an `AsyncEngine`; `create_table=False` hands DDL to Alembic. owner resolves to `""`
  today via `UnauthenticatedUser` (fine; resolver swappable at auth time).
- `ListTasks`/`GetTask` remain available for the *reconnect* path (dropped-stream
  recovery), but are **no longer the conversation-history source** — history reads come
  from the repository.
- JS `@a2a-js/sdk` client exposes `listTasks`; `deleteTask` shape to verify before use.

## Slices (repo's PR-per-slice style; each ships with tests, pyright + vitest green)

### PR A — Alembic harness + durable task store ✅ DONE
Mirrors gcm's Story-1 structure, adapted to async Postgres.
- `apps/a2a-server/`: `alembic.ini` (`script_location`, `prepend_sys_path = src`, dummy
  `sqlalchemy.url`), `alembic/env.py` **async** (`create_async_engine` +
  `connection.run_sync(do_run_migrations)`, `compare_type=True`), `script.py.mako`,
  `alembic/versions/0001_baseline_a2a_tasks.py` (hand-written per schema above).
- New shared config/engine module (e.g. `infrastructure/db/engine.py`) reading
  `DATABASE_URL` fail-loud, imported by both `env.py` and the app lifespan.
- `main.py` lifespan: build the shared `AsyncEngine`, construct
  `DatabaseTaskStore(engine, table_name="a2a_tasks", create_table=False,
  owner_resolver=resolve_user_scope)`, `await store.initialize()`, stash on `app.state`;
  dispose engine on shutdown. `api/dependencies.py` seam unchanged.
- `pyproject.toml`: `a2a-sdk[postgresql]==1.1.2` (verify the asyncpg extra name),
  `sqlalchemy`, `alembic`, `asyncpg` pins. `docker-compose.yml` for local Postgres.
- Migrations run as a **pre-start step** (`alembic upgrade head`), never at FastAPI
  startup.
- Tests: existing cases keep the InMemory override via `app.dependency_overrides` (no DB).
  Add a durability test gated on `DATABASE_URL` (skipped otherwise) against the compose
  Postgres: save task → GetTask/ListTasks-by-contextId round-trip across a fresh store.

### PR B — ConversationRepository + tables ✅ DONE
(Shipped `content` + `message_json` split — `content` is always the user-facing text, agent
prose; `message_json` is JSONB, the full AgentAnswer, null for user turns. Columns spelled
`timestamp`/`sequence`.)
- `alembic/versions/0002_add_conversation_tables.py` (hand-written; depends on 0001):
  `conversations` + `conversation_messages` with FK CASCADE + `(conversation_id, seq)`
  index + `UNIQUE(conversation_id, seq)`.
- `infrastructure/db/models/base.py` (shared `Base`), `models/conversation.py`
  (`ConversationRow`/`ConversationMessageRow`), `repositories/conversations.py`
  (`ConversationRepository`: async `get`, `append_message`, `delete`, `summarize_if_needed`;
  raises `ConversationNotFoundError`). DTOs (`Conversation`/`ConversationMessage`) in the
  application/domain layer, frozen pydantic — no bare `dict` (CLAUDE.md).
- Lifespan builds the repo on the shared engine, stashes `app.state.conversations` before
  routes accept traffic.
- A2A executor: translate `conversation_id = context.context_id`; persist the user turn
  and the assistant answer via `append_message` at the right points in `execute()` (the
  `AgentAnswer.model_dump_json()` already assembled is the assistant payload).
- Tests: repository against compose Postgres (gated) — append ordering under concurrent
  appends (no seq collision), CASCADE delete, `ConversationNotFoundError`, restart
  survival, atomic trim (no torn read).

### PR C — history read path (transport) + rehydration ✅ DONE
(Chose the REST controller. Also added the `/conversations` Vite dev-proxy rule.)
- Decide the read surface: either an A2A-side method or a thin `GET /conversations/{id}`
  and `GET /conversations` controller returning `Conversation` DTOs (404 → `ErrorResponse`,
  no exception leak, per CLAUDE.md). **Recommend** the small REST controller — it's the
  clean product API and keeps A2A for the agent turn only.
- `apps/web/src/api/agentApi.ts` (or a new `conversationsApi.ts`): `listConversations()` +
  `getConversation(id)` hitting the read surface; pure `turnsFromConversation(dto)`
  rebuilding `Turn[]` (reuse `parseAgentAnswer`, `messageText`). Pure → unit-testable with
  injected DTOs.
- Tests: pure rebuild fns with injected DTOs, like the existing `recoverEventsFromTask`
  tests.

### PR D — sidebar UI + switching ✅ DONE
(Went further than remount-on-key alone: added `react-router-dom` so the **URL is the source
of truth** — routes `/` and `/c/:conversationId`; frontend speaks `conversationId`, the A2A
`contextId` stays internal to `useA2AChat`. Switching remounts the keyed `<Chat>`.)
- **State:** keep `useA2AChat` single-conversation; **remount on switch via React
  `key={activeConversationId}`** + a new `useConversations` hook. Preserves the
  `streamFn`/`recoverFn` DI seam and every existing hook test. Hook gains `initialContextId`
  / `initialTurns` for rehydration. New chat = mount with `contextId=""` + empty turns.
  Replace the single `christ-mind.agent.contextId` sessionStorage key with active-id
  tracking.
- **UI:** `App.tsx` outer `flex h-dvh flex-col` → `flex h-dvh` row with a hand-rolled
  `Sidebar` left pane (list, new-chat button, active highlight) — inline SVG + local `cn`
  + OKLCH tokens, matching `ui/button.tsx`; **no Radix/shadcn**. Existing column becomes
  the right pane; keep `App`'s `streamFn`/`recoverFn` props seam intact.
- Tests: `useConversations` + switching via injected seams; `Sidebar` with `data-testid` +
  `userEvent`.

### PR E — rename + delete ✅ DONE
(Inline pencil-rename + two-step delete-confirm; delete-active → navigate to `/`. Blank
rename → 422; delete idempotent → 204. Open decision resolved: `a2a_tasks` rows are NOT
pruned on conversation delete — left as harmless orphans.)
- **Rename:** `summarize`/title override — server-side update to `conversations.summary`
  via the repository (a small `PATCH`/method), hand-rolled inline-edit in the sidebar.
- **Delete:** `DELETE /conversations/{id}` → `ConversationRepository.delete` (FK CASCADE
  removes messages); hand-rolled confirm. Subsequent `GET` returns 404.
- Tests: delete cascades + 404-after-delete (backend); inline-edit + confirm (frontend).

## Key files
- `apps/a2a-server/alembic.ini`, `alembic/env.py`, `alembic/versions/0001_*.py`,
  `alembic/versions/0002_*.py`
- `apps/a2a-server/src/mind_of_christ_a2a/infrastructure/db/engine.py`, `models/base.py`,
  `models/conversation.py`, `repositories/conversations.py`
- `apps/a2a-server/src/mind_of_christ_a2a/main.py`,
  `api/controllers/conversations_controller.py`, `domain/a2a/executor.py`
- `apps/a2a-server/pyproject.toml`, `docker-compose.yml`
- `apps/web/src/api/agentApi.ts` (+ maybe `conversationsApi.ts`),
  `hooks/useA2AChat.ts`, new `hooks/useConversations.ts`, `App.tsx`,
  new `components/chat/Sidebar.tsx`

## Verification
- **PR A:** `pytest apps/a2a-server/tests -q` + `pyright`; start with `DATABASE_URL` unset
  → fail-loud; bring up compose Postgres, `alembic upgrade head`, send a turn, restart the
  process, `GetTask`/`ListTasks` still return the prior task.
- **PR B:** repo tests (gated) green; two turns with the same `contextId`, restart,
  `conversation_messages` still hold both in `seq` order.
- **PR C–E:** `cd apps/web && npm test` + build; per-slice pyright/vitest green.
- **End-to-end (browser, per the jsdom caveat):** backend with `AGENT_PUBLIC_URL` +
  `DATABASE_URL=<compose Postgres>`, Vite dev server; create two conversations, refresh
  (both persist + rehydrate from the repo), switch (turns restore, reconnect still works),
  rename, delete (404 after).

## Risks / unknowns — how they resolved
- asyncpg extra: pinned `a2a-sdk[postgresql]==1.1.2` + `asyncpg==0.31.0`, `sqlalchemy==2.1.1`,
  `alembic==1.20.0` (PR A).
- `seq` (shipped as **`sequence`**) concurrency: `UNIQUE(conversation_id, sequence)` +
  bounded retry on `IntegrityError`, allocate-and-insert in one transaction. Proven by a
  12-way concurrent-append test (contiguous unique 1..12).
- `a2a_tasks` pruning on conversation delete: **decided NO** — task rows are left as harmless
  orphans keyed by the same context_id; not pruned. (JS `deleteTask` never needed — delete
  goes through the repository, not the task store.)
- owner `""` = all local conversations in one bucket (still fine; resolver swappable at auth).
- jsdom has no real layout — sidebar/rename/delete logic is unit-tested; row-layout feel
  verified in the browser.
- No-self-commit honored throughout: each slice implemented + staged; the user committed.

## Post-completion bug fixes (during testing)
- **Retry-after-stop:** stopping before the first token dropped the empty agent bubble, then
  reconnect wrote the recovered reply into the missing turn id (vanished). `handleReconnect`
  now recreates the bubble; `handleCancel` clears in-flight guards synchronously. Also fixed
  PR A's durability test (UUID column overflow + two-store model-redefinition + honest DB gate).
- **New-chat stale transcript (PR D):** `seeds` lagged the route change so the keyed `<Chat>`
  seeded from the previous conversation. Now reset **during render** on `conversationId` change.
