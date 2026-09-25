# mind-of-christ-web

The user-facing chat app: a full-window, ChatGPT-style surface where a person describes a
situation and receives an answer grounded in cited A Course in Miracles claims, kept
distinct from what the agent infers. React + Vite + Tailwind v4 + TypeScript. Talks A2A
(native v1) to `apps/a2a-server`.

Not part of the Python packages — its own `package.json` and toolchain.

## Setup

```sh
cd apps/web
npm install
```

## Run (full stack)

Two processes. **Start the backend first**, and — this is the load-bearing detail — set
`AGENT_PUBLIC_URL` to the **Vite dev origin**, not the backend's own port:

```sh
# repo root — the a2a-server (see apps/a2a-server for install + hot reload)
AGENT_PUBLIC_URL=http://localhost:5173 .venv/bin/python -m mind_of_christ_a2a.main
```

```sh
# apps/web — the Vite dev server on :5173
npm run dev
```

Open `http://localhost:5173`, type a situation, and send.

### Why `AGENT_PUBLIC_URL=http://localhost:5173`

The A2A client reads the agent card first, then dials the **absolute** endpoint URL the
card advertises (`<AGENT_PUBLIC_URL>/a2a`). Vite proxies both `/a2a` and `/.well-known` to
the backend (`:8000`, see `vite.config.ts`). Pointing `AGENT_PUBLIC_URL` at `:5173` makes
the card advertise the proxied origin, so the card fetch **and** streaming stay same-origin
through the proxy — no CORS, no backend change. Pointing it at `:8000` would make the client
bypass the proxy and hit CORS.

`VITE_AGENT_BASE_URL` overrides the client's base URL (defaults to the page origin); leave
it unset for the proxy setup above.

## Test & build

```sh
npm test          # vitest run
npm run build     # tsc -b && vite build
```

## Layout

- `src/api/agentApi.ts` — the A2A transport (`@a2a-js/sdk`). `eventsFromFrame` routes the
  streamed `answer` artifact to text deltas and the `evidence` artifact to a parsed
  `AgentAnswer` (cited claims + inferred chains).
- `src/hooks/useA2AChat.ts` — chat state; a `Turn` carries both streamed prose and the
  structured answer. Injectable `streamFn` seam for tests.
- `src/components/chat/` — `Composer`, `Transcript`, `MarkdownMessage`, and `CitedAnswer`
  (renders the Course-says / what-follows distinction).
