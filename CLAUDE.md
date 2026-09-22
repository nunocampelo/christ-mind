# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A monorepo (root `christ/`, apps under `apps/`) currently holding one package:
**`mind-of-christ-mcp`** (`apps/mcp-server/`), an **MCP (Model Context Protocol) server**
exposing the "Mind of Christ" knowledge system as tools for an LLM agent to call over
stdio. It is not an HTTP service — there's no FastAPI/web layer here.

This is an early prototype slice, not the target architecture. The current tool set is one
function, `find_sources`, backed by a small in-memory stub of public-domain (KJV) source
passages — not a real datastore. Per `apps/mcp-server/README.md`, not yet built: real
database-backed repositories, additional tools (e.g. `explore_situation`), an
orchestrator/agent layer, an A2A interface, and an evaluation harness. Expect more apps to
land under `apps/` as that architecture is built out — keep each app self-contained with
its own `pyproject.toml`, sharing only the root `.venv`.

Imports inside `apps/mcp-server` are bare-package (`from mind_of_christ_mcp.tools import
find_sources`), since the package installs editable (`pip install -e`) with `src/` as the
layout root. Tests import the same way.

## Style

**Comments only when they add information the code cannot.** Do not annotate blocks with a
preamble describing what the next few lines do, and do not restate what a function or
variable name already tells the reader. Add a comment only when a competent reader would
still be confused — a subtle invariant, a non-obvious workaround, or a "why this and not
the obvious alternative". Applies equally to `src/` and `tests/`. If in doubt, delete the
comment. `data.py` and `tools.py` already follow this — module docstrings explain *why* a
piece is a placeholder, not what each line does.

## Formatting

No formatter or linter is configured yet (no `black`/`ruff`/`flake8` in `pyproject.toml`'s
`dev` extra). Match the existing style (double quotes, trailing commas in multi-line
literals, ~88-char lines) by hand until one is adopted. When a formatter/linter is added,
it becomes the source of truth — run it before finishing any change and don't hand-format
around it or weaken its config to silence a warning.

## Typing

`requires-python = ">=3.12"`; the checked-in `.venv` runs 3.14.7. **Use the modern, native
syntax** — `list[X]` / `dict[K, V]`, `X | None` — never `typing.List`/`typing.Optional`.
No type checker (`mypy`/`pyright`) is configured yet; if one is added, run it before
finishing a change, fix every error by tightening the annotation or narrowing with
`isinstance`, and reserve a scoped `# type: ignore[code]` (never bare) for genuine
checker limitations.

Keep tool-facing shapes typed: `find_sources` returns `list[Source]` (a frozen dataclass in
`data.py`), and the MCP tool wrapper in `server.py` is the one place that flattens it to
`list[dict]` for the wire — that conversion doesn't belong in `tools.py`.

## Logging

Not used anywhere in the codebase yet (no `print`, no `logging`/`loguru`). If the server
grows behavior worth logging (tool call failures, retrieval misses worth tracking), install
one logger configured once at startup, log static messages with values as structured
fields (not f-strings), and follow the level guidance below:

- `DEBUG` — troubleshooting detail a caller can't reconstruct.
- `INFO` — business-relevant events, not every branch.
- `WARNING` — a situation that may cause errors later.
- `ERROR` — a failure that degrades functionality but the process keeps running.
- `CRITICAL` — unrecoverable; the process is going down.

## Error handling

Current code has no error handling to speak of — `find_sources` degrades to `[]` on no
match by design (see Tests), not by swallowing an exception. As real I/O (a datastore,
upstream calls) is introduced:

- **Catch the narrowest exception the caller can raise, not `Exception`.** A blanket catch
  sweeps up programming errors (a typo, a call to a deleted helper) and silently turns them
  into a generic failure instead of a visible test failure.
- **Re-raise as a domain-specific error with a static message**, chained with `from e` so
  an upstream log still prints the full original traceback. Never interpolate the caught
  exception's text into the new message — that text can carry request payloads or internal
  paths, and it will resurface wherever the new exception is logged or returned.
- **Fail loud rather than default silently.** A missing required env var or config value
  should raise at startup, not fall back to a placeholder.

## Commands

```bash
# From the repo root

# Create/refresh the venv (already created at .venv/; see apps/mcp-server/README.md)
python3.14 -m venv .venv

# Install the mcp-server package, editable, with dev deps
.venv/bin/pip install -e "apps/mcp-server[dev]"

# Run tests
.venv/bin/python -m pytest apps/mcp-server/tests -q

# Run the server (stdio) — point an MCP client (Claude Desktop, MCP inspector) at this
.venv/bin/python -m mind_of_christ_mcp.server
```

There is no `.env`/config loading yet — the server takes no external configuration.

## Dependencies

`apps/mcp-server/pyproject.toml` currently pins with `>=` (`mcp>=1.2.0`,
`pytest>=8.0.0`), which is fine for a prototype with no deployment target. Once this ships
anywhere (a container, a scheduled process), switch to exact pins (`pkg==X.Y.Z`) so a cold
install can't silently pull in a breaking release — tests pass on version X locally but the
shipped build comes up on X+1.

**When adding a new dependency:** install it locally to find the version you need, add it
to `dependencies` (or the `dev` extra) in `pyproject.toml`, and re-run
`pip install -e "apps/mcp-server[dev]"`. If something you already `import` isn't declared,
add it — arriving transitively via `mcp` or another dep is not declaring it.

## Tests

`apps/mcp-server/tests/test_tools.py` imports `tools.find_sources` directly and asserts
against the returned `Source` dataclasses — no MCP transport in the loop. Keep following
that pattern: **tool logic lives in `tools.py` precisely so it can be tested without the
MCP server**, per its own module docstring. If `server.py`'s wrapper (the dict-flattening,
tool registration) grows logic beyond a straight pass-through, add tests around it too,
mocking the MCP transport rather than `tools.py`.

**Prefer equality/membership assertions that would catch a real regression** over vague
truthiness — e.g. `all("forgiveness" in source.concepts for source in results)`, not just
`assert results`. The existing empty-query and no-match tests already encode `find_sources`
returning `[]` as *intentional behavior*, not an oversight — preserve that if you touch the
function.

## Architecture

Minimal today, not yet DDD-layered — there's exactly one tool, so don't over-structure
ahead of need:

- `src/mind_of_christ_mcp/server.py` — entrypoint only: builds the `MCPServer`, registers
  tools via `@mcp.tool()`, and does the wire-shape conversion (dataclass → `dict`) for each
  one. Stays thin — no retrieval logic here.
- `src/mind_of_christ_mcp/tools.py` — tool implementations, deliberately independent of the
  MCP transport so they're unit-testable directly (see Tests). This is where new tools
  (`explore_situation`, etc., per the README's roadmap) should be added as plain functions,
  registered in `server.py`.
- `src/mind_of_christ_mcp/data.py` — stub in-memory `SOURCES`, explicitly a placeholder for
  a real repository/infrastructure layer. When a real datastore arrives, it should sit
  behind the same `find_sources`-style function signature so `tools.py` and `server.py`
  don't need to change shape — only what backs them.

**Push work to its natural layer as the app grows**: retrieval/query logic belongs in the
future repository layer, not duplicated in `tools.py`; wire-shape conversion belongs in
`server.py`, not leaked into `tools.py`'s return types.

## Deployment

None yet — this is a local prototype run over stdio for manual/agent testing. No CI, no
container, no secrets. Document the pipeline here once one exists (see the base template
this file was generated from for the shape: CI on push, container build, orchestrator
secrets, migrations-before-app if a real datastore is added).
