# christ

"Mind of Christ" is a knowledge system for retrieving source passages
(scripture, A Course in Miracles, and other texts) relevant to a query, meant
to be called by an LLM agent. This repo is a DDD-layered monorepo: shared
domain/application/infrastructure code in `src/`, with thin transport-specific
apps in `apps/` calling into it.

## Layout

- `apps/mcp-server/` — **`mind-of-christ-mcp`**, an MCP (Model Context
  Protocol) server exposing the knowledge system as tools for an agent to
  call over stdio. Not an HTTP service. More apps (`agent/`, `a2a-server/`)
  will land here as the orchestrator/agent layer and A2A interface are built.
- `src/domain/sources/` — the `Source` frozen dataclass: the entity itself,
  no behavior, no storage or transport concerns.
- `src/application/retrieval/` — `find_sources`, the use case matching a
  query against the source repository. Kept independent of any transport so
  it's unit-testable directly.
- `src/infrastructure/database/` — the source repositories: `sources.py`
  aggregates `sources_bible.py` (small in-memory stub of public-domain KJV
  text) and `sources_acim.py` (parses the markdown chapter files under
  `data/acim/` into `Source` objects at import time). Both are placeholders
  for a real datastore.
- `src/domain/claims/` — the `Claim` frozen dataclass: one assertion a
  passage makes (subject, predicate, object, polarity, mode, attribution),
  with evidence offsets into the source text.
- `evaluation/claims/` — hand-labelled gold claims (`gold/*.jsonl`) and a
  scorer for claim extraction runs. The extractor itself isn't built yet.

`src/domain/`, `src/application/`, and `src/infrastructure/` are one shared,
installable package (`mind-of-christ`) that `apps/mcp-server` depends on.
See `CLAUDE.md` for the full architectural rationale and conventions.

## Setup

```sh
python3.14 -m venv .venv

# Install the shared domain/application/infrastructure package first —
# apps/mcp-server depends on it being registered in the venv.
.venv/bin/pip install -e ".[dev]"
.venv/bin/pip install -e "apps/mcp-server[dev]"
```

## Run tests

```sh
.venv/bin/python -m pytest tests -q                       # domain/application/infrastructure
.venv/bin/python -m pytest apps/mcp-server/tests -q        # MCP wire-boundary tests
```

## Type-check

```sh
.venv/bin/pyright   # covers root src/, root tests/, and apps/mcp-server/src
```

## Run the server (stdio)

```sh
.venv/bin/python -m mind_of_christ_mcp.server
```

Point an MCP client (Claude Desktop, the MCP inspector, a custom client) at
this command over stdio to connect.

To inspect the server interactively with the
[MCP inspector](https://github.com/modelcontextprotocol/inspector) (requires
Node.js):

```sh
npx @modelcontextprotocol/inspector .venv/bin/python -m mind_of_christ_mcp.server
```

## Tools

- `find_sources(query, limit=5)` — keyword/concept search over the source
  set (Bible + ACIM), returning matching passages with their book/chapter/verse
  (or section/paragraph) locator and concept tags.

## Status

This is a prototype, not the full architecture. Not yet built: a real
database-backed repository (both source sets are still stub/file-parsed
in-memory data), additional tools (`explore_situation` and friends), the
orchestrator/agent layer, the A2A interface, and the claim extractor that
the `evaluation/claims` scorer is waiting on. No
CI, no container, no deployment pipeline yet.
