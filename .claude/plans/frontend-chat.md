# Frontend chat — Incremental PR Plan (vertical slices)

## Context

christ-mind's user-facing surface is a standalone, full-window **ChatGPT-style** chat app: a
person types a situation ("I keep getting angry when criticized"), and the agent streams back
an answer grounded in cited Course claims, keeping "the Course says X" distinct from "this
follows". This is a **port of a proven, shipped chat-app PR plan** (7 vertical slices, merged
through PR 4 in its origin project): reuse its architecture, strip everything specific to that
project's host stack.

**Hard prerequisite:** this frontend talks A2A to `apps/a2a-server`, which does not exist yet.
It is built **after** the backend slices in `agent-layer-and-a2a-backend.md` (PR 1 revert →
PR 2 `apps/agent/` orchestrator → PR 3 `apps/a2a-server/`). Until then, every slice below is
developed against an **injected `streamFn` stub** (the plan's existing seam), so UI work can
progress and be tested without a live agent — but "done" for each slice means it works against
the real A2A server once it lands.

**Stack (locked):** React + Vite + Tailwind v4 + **shadcn/ui** (Radix primitives, component
source copied into the repo, styled with our own Unima design tokens — no vendor web-component
kit, no vendor theme to fight). Transport unchanged from the reference plan: `@a2a-js/sdk`,
`react-markdown` + `remark-gfm`. Tests ship **with** each slice (full-component integration
tests, vanilla Cypress or Vitest + Testing Library — no vendor-specific test commands).

**Where it lives:** a new app, `apps/web/` (its own `package.json`, Vite config, not part of
the Python packages). Mirrors the monorepo convention of self-contained apps under `apps/`.

## What ports unchanged vs. what is swapped

| Reference plan (embedded side-panel) | christ-mind (full-window, Unima) |
| ------------------------------------ | -------------------------------- |
| `agentApi.ts`, `useA2AChat.ts`, `@a2a-js/sdk`, `streamFn` seam, markdown, typewriter, contextId | **Unchanged** — pure transport/state, port as-is |
| vendor web-component kit (app-shell bar, message strip) | shadcn/ui (Radix) + our tokens |
| vendor theme vars in Tailwind arbitrary values | our Unima design tokens |
| host-specific CSRF fetch wrapper | plain fetch / whatever a2a-server needs (likely nothing) |
| app-shell-bar toggle → `<aside>` panel | the app **is** the chat: root route, full viewport |
| Panel empty-state splash | full centered landing screen |

## Design decisions carried in

- **Full-window, not a panel.** No host shell, no toggle. Centered conversation column, sticky
  bottom composer, full-screen landing empty state. The reference plan's PR 1 ("open the panel") becomes "the
  chat page renders" — the whole app skeleton.
- **Single conversation first.** One thread, persisted across refresh via `contextId`
  (sessionStorage, like the reference plan's PR 4). The ChatGPT-style **multi-conversation sidebar** (new chat /
  switch / rename / delete) is deferred — it needs a backend conversation list/persist API
  beyond raw A2A, so it is a later slice with its own backend work.
- **Cited vs. inferred is a first-class UI concern.** The agent's answer separates cited Course
  claims (with `source_id`) from inferred chains; the UI must render that distinction visibly
  (e.g. citations styled/linked, inferred synthesis marked), never flatten them into one blob.
  This is the frontend end of the system-wide invariant.
- **`streamFn` seam for testability.** `useA2AChat` takes an injectable `streamFn` (default: the
  real `streamAssistant`), so every slice is component-tested without a live agent.

---

## PR 1 — The chat app renders (shell only, no sending yet)

**User sees:** opening the app shows a full-window landing screen — greeting, title, and a
centered composer (auto-growing textarea + send button). Input is inert/disabled; nothing
sends. First honest, visible surface.

**Ships:**
- `apps/web/` scaffold: Vite + React + TS, Tailwind v4, shadcn/ui initialized with Unima
  design tokens (colors/spacing/radius/font as CSS vars, dark + light).
- `App.tsx` / root route: full-viewport layout, centered conversation column, sticky composer.
- `ChatLanding.tsx`: centered empty state (greeting + title). **No prompt cards** (deferred,
  like the reference plan — they only make sense once sending works).
- `Composer.tsx` + `AutoGrowTextarea` (shadcn textarea + button; send disabled for now).
- Un-utility-able bits (gradient-clipped title, glow, `prefers-reduced-motion`) in a
  component-scoped companion stylesheet, not global.
- **No `@a2a-js/sdk` / markdown deps yet** (move in with PR 2).

**Tests:** renders greeting + title; composer visible; send disabled.

## PR 2 — Ask a question and get an answer (working, no smoothing)

**User sees:** typing + Send (or Enter) posts the message; the agent's markdown reply appears.
Text arrives at once (no typewriter yet). Genuinely usable against the real agent.

**Ships:**
- `agentApi.ts`: `getClient`, `AgentStreamEvent`, `streamAssistant`, and `eventsFromFrame` for
  the full answer path — **`task` + `artifactUpdate` (artifact_id="answer") + `statusUpdate` +
  `message` + error** (the real agent streams the answer via `artifactUpdate`, so this can't be
  split from "make it work"). No `csrfFetch` — plain fetch.
- `useA2AChat.ts`: `Turn` model, `send`/`handleSubmit`/`handleInputKeyDown`, `consumeStream`,
  append user + agent turn, `removeAgentTurnIfEmpty`, double-submit guard, error surfacing,
  injectable `streamFn` seam.
- `MarkdownMessage.tsx` + markdown typography styles in the companion stylesheet.
- `CitedAnswer.tsx`: renders the agent turn splitting **cited claims (with source_id)** from
  **inferred chains** — the invariant, visible. (Depends on the answer DTO fixed in backend PR 2.)
- Transcript wiring in the conversation column: user/agent bubbles.
- deps: `@a2a-js/sdk`, `react-markdown`, `remark-gfm`.

**Tests (inject `streamFn`):** ask → user bubble + markdown reply; Enter/Shift+Enter; disabled-
when-empty; error strip; empty bubble removed when nothing returns; `eventsFromFrame` mapping
per payload case; cited vs. inferred rendered distinctly.

## PR 3 — Streamed, typewriter-style answers

**User sees:** the answer types in smoothly, with a "thinking" indicator before the first
token, instead of appearing all at once. Feels live.

**Ships:** `useSmoothText.ts` reveal hook + `AgentBubble` wiring (typing dots while empty/
streaming); `consumeStream` finalizes on terminal state; typing-dots keyframes +
`prefers-reduced-motion` opt-out in the companion stylesheet.

**Tests:** big blob reveals over frames; `done`/reduced-motion snaps; dots show pre-first-delta.

## PR 4 — Multi-turn memory across the conversation (and refresh)

**User sees:** follow-ups remember context; a page refresh keeps the same thread.

**Ships:** `useA2AChat.ts` `contextId` state + sessionStorage persistence, echoed on each turn;
`contextId` event handling in `consumeStream`; `agentApi.ts` emits `contextId` from the `task`
frame.

**Tests:** `contextId` persisted + echoed on next turn; rehydrated on mount; second turn sends
the stored id.

## PR 5 — Stop a running answer

**User sees:** while streaming, Send becomes Stop; clicking halts the stream and drops an inline
"Request stopped" notice, keeping the partial answer.

**Ships:** `useA2AChat.ts` `abortRef` (controller doubles as in-flight flag), `handleCancel`,
`notice`-role turns, `!signal.aborted` guard so a user abort isn't surfaced as an error;
`Composer` send↔stop toggle; `streamAssistant` accepts a `signal` and returns early on abort.

**Tests:** stop mid-stream aborts, shows notice, restores Send, retains partial; empty bubble
dropped when stopped before first token; no error strip on user stop.

## PR 6 — Recover a dropped answer (reconnect)

**User sees:** if a stream drops, a refresh chip appears on the notice; clicking replays the
finished answer into the same bubble via GetTask polling.

**Ships:** `agentApi.ts` `recoverAssistant`, `answerSoFar`, `ANSWER_ARTIFACT_ID`, chunked-drain
consts; `useA2AChat.ts` `lastTaskId`, `resetLastAgentTurn`, `handleReconnect`; reconnect chip on
the tail notice.

**Tests:** `recoverAssistant` polls, emits chunked suffix, COMPLETED ends / FAILED→error /
cap→timeout; reconnect refills same bubble; chip only on tail notice.

## PR 7 — Polished scroll & anchoring UX

**User sees:** the newest question anchors near the top with a settling tail spacer, so long
answers don't jump the viewport. (More prominent than in the reference plan — this is a full-window app.)

**Ships:** `useA2AChat.ts` `recomputeSpacer`/`anchorNewestUserTurn`/`ResizeObserver` +
`spacerHeight`; tail-spacer markup in the conversation column.

**Tests:** newest user turn anchored; spacer collapses when idle.

---

## Deferred beyond this plan (their own later slices)

- **Multi-conversation sidebar** (new chat / switch / rename / delete) — the ChatGPT hallmark.
  Needs a backend conversation list/persist API beyond raw A2A `contextId`; a coordinated
  frontend + `apps/a2a-server` slice, planned when we get there.
- **Prompt suggestion cards** on the landing screen — move in once sending works (a small slice
  after PR 2), matching the reference plan's deferral.
- **Auth/identity** in the transport — lands when a2a-server carries a real token.

## Why this order

- **PR 1** = smallest shippable, visible surface (the app renders).
- **PR 2** makes it actually work (ask → cited answer against the real agent).
- **PR 3–4** make it feel and behave like a real chat (streaming, memory).
- **PR 5–6** add control and resilience (stop, reconnect).
- **PR 7** polishes the full-window scroll UX.

Styling is not a separate PR: each slice ships its UI already in Tailwind + shadcn, extending
the component-scoped companion stylesheet only for what utilities can't express (PR 2 markdown
typography, PR 3 typing-dots keyframes). `agentApi.ts` + `useA2AChat.ts` grow across PRs 2–6,
each adding only the cases its slice needs. Every PR leaves a demoable app. Git commits left to
the user (no self-commit).
