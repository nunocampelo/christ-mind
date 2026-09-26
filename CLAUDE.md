# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A monorepo (root `christ/`) that is now DDD-layered:

- `apps/` — thin, transport-specific interfaces. Currently one: **`mind-of-christ-mcp`**
  (`apps/mcp-server/`), an **MCP (Model Context Protocol) server** exposing the "Mind of
  Christ" knowledge system as tools for an LLM agent to call over stdio. Not an HTTP
  service — there's no FastAPI/web layer here. More apps (`agent/`, `a2a-server/`) will
  land here as the orchestrator/agent layer and A2A interface are built; only create an
  app directory once it has real code, not as an empty scaffold.
- `src/domain/` — entities and business rules, transport- and storage-agnostic. Currently
  `src/domain/sources/` (the `Source` dataclass) and `src/domain/claims/` (the `Claim`
  dataclass and its closed `Predicate`/`Polarity`/`Mode`/`Attribution` enums).
- `src/application/` — use cases that orchestrate domain objects against a repository.
  Currently `src/application/retrieval/` (`find_sources`) and
  `src/application/extraction/` (`extract_claims`).
- `src/infrastructure/` — concrete backing for the domain/application layers. Currently
  `src/infrastructure/database/` (`list_sources`, an in-memory stub — see Architecture).
- `evaluation/` — measures claim extraction against hand-labelled data.
  `evaluation/claims/gold/*.jsonl` holds gold claims, which name evidence by exact text;
  `gold.py` resolves that to offsets in the parsed `Source.text` and fails loudly if the
  text moved. `score.py` reports loose (triple) and strict (+ polarity/mode/attribution)
  precision/recall. Not an installed package — importable from the repo root, which is
  where pytest and pyright run.

`src/domain/`, `src/application/`, and `src/infrastructure/` are one shared, installable
package (`mind-of-christ`, root `pyproject.toml`, `where = ["src"]` in its
`[tool.setuptools.packages.find]`) that `apps/mcp-server` depends on — unlike `apps/`, they
are **not** self-contained per-app code; that's the point of pulling shared logic out of
`apps/mcp-server` in the first place. Everything still shares the one root `.venv`. The
package names stay bare (`domain`, `application`, `infrastructure`, no `src.` prefix) —
`src/` is only a layout root, exactly like `apps/mcp-server/src/`.

**Every `__init__.py` in this repo is empty — no re-exporting.** Imports always name the
actual module a symbol is defined in, never the enclosing package:
`from domain.sources.models import Source`, `from application.retrieval.find_sources import
find_sources`, `from infrastructure.database.sources import list_sources`, and inside
`apps/mcp-server`, `from application.retrieval.find_sources import find_sources` and `from
mind_of_christ_mcp.schemas.sources import SourceResult`. This trades a shorter import path
for one that's unambiguous about where a symbol actually lives, and it means a package's
`__init__.py` never becomes a second place a new export has to be wired up. Both the root
package and `apps/mcp-server` install editable (`pip install -e`), each with its own `src/`
as its layout root. Tests import the same way.

## Style

**Comments only when they add information the code cannot.** Do not annotate blocks with a
preamble describing what the next few lines do, and do not restate what a function or
variable name already tells the reader. Add a comment only when a competent reader would
still be confused — a subtle invariant, a non-obvious workaround, or a "why this and not
the obvious alternative". Applies equally to both `src/` trees (root and
`apps/mcp-server/`) and `tests/`. If in doubt, delete the comment.
`src/infrastructure/database/sources.py` already follows this — its module docstring
explains *why* it's a placeholder, not what each line does.

**Be sparse — this covers docstrings and module docs too, not just inline comments.**
Default to no comment. Write one only for what the code genuinely cannot convey: a
non-obvious *why*, an invariant a reader would otherwise violate, a pitfall/workaround worth
flagging for the future. Keep module docstrings short — a line or two of intent, not a
narration of every method and branch below. Do not write multi-paragraph docstrings that
restate the code; if the prose just re-says what the names and types already say, cut it.

## Formatting

No formatter or linter is configured yet (no `black`/`ruff`/`flake8` in `pyproject.toml`'s
`dev` extra). Match the existing style (double quotes, trailing commas in multi-line
literals, ~88-char lines) by hand until one is adopted. When a formatter/linter is added,
it becomes the source of truth — run it before finishing any change and don't hand-format
around it or weaken its config to silence a warning.

## Typing

`requires-python = ">=3.12"`; the checked-in `.venv` runs 3.14.7. **Use the modern, native
syntax** — `list[X]` / `dict[K, V]`, `X | None` — never `typing.List`/`typing.Optional`.

**`pyright` is configured** (root `pyproject.toml`'s `[tool.pyright]`, `dev` extra of the
root package), `typeCheckingMode = "standard"`, covering root `src/`, root `tests/`, and
`apps/mcp-server/src`. Run `.venv/bin/pyright` from the repo root before finishing any
change; fix every error by tightening the annotation or narrowing with `isinstance`, and
reserve a scoped `# type: ignore[code]` (never bare) for genuine checker limitations.

Keep tool-facing shapes typed: `find_sources` returns `list[Source]` (a frozen dataclass in
`src/domain/sources/models.py`), and the MCP tool wrapper in `apps/mcp-server`'s `server.py`
is
the one place that converts it to the wire type for each tool — that conversion doesn't
belong in `application/retrieval`.

**No bare `dict`/`dict[K, V]` in a tool's return type.** Every MCP tool return type is a
`pydantic.BaseModel` defined under `apps/mcp-server/src/mind_of_christ_mcp/schemas/` (e.g.
`SourceResult` in `schemas/sources.py`, for `find_sources`), never a raw `dict`. A `dict` return type gives up field
names, types, and the schema the MCP client sees for free validation — a typo'd key or a
dropped field fails silently instead of at construction. The `server.py` wrapper builds the
model from the domain dataclass field-by-field; new tools follow the same pattern rather
than reusing an existing model for an unrelated shape.

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

# Install the shared domain/application/infrastructure package (src/), editable, with dev
# deps (pytest, pyright) — install this first, apps depend on it
.venv/bin/pip install -e ".[dev]"

# Install the mcp-server package, editable, with dev deps
.venv/bin/pip install -e "apps/mcp-server[dev]"

# Run tests (domain/application/infrastructure)
.venv/bin/python -m pytest tests -q

# Type-check everything (root src/ + apps/mcp-server/src)
.venv/bin/pyright

# Score a claim extractor against the dev gold set (add --holdout only to report a
# result, never while tuning); writes evaluation/claims/runs/<run_id>.jsonl — commit it
.venv/bin/python -m evaluation.claims.run --extractor my_pkg.my_module:make_extractor

# Run the server (stdio) — point an MCP client (Claude Desktop, MCP inspector) at this
.venv/bin/python -m mind_of_christ_mcp.server
```

There is no `.env`/config loading yet — the server takes no external configuration.

## Dependencies

Both `pyproject.toml`s pin exact versions (root: `pytest==9.1.1`, `pyright==1.1.414`;
`apps/mcp-server`: `mcp==2.2.0`, `mind-of-christ==0.1.0`, `pydantic==2.13.5`,
`pytest==9.1.1`) so a cold install can't silently pull in a breaking release — tests
passing on version X locally is no guarantee once a cold install lands on X+1. When
bumping a pin, install the new version locally, run the full test suite and `pyright`
against it, and only then update the `==` in the relevant `pyproject.toml`.

`apps/mcp-server`'s dependency on `mind-of-christ` is a same-repo path install, not a
published package: it's satisfied by whatever the root `pyproject.toml -e ".[dev]"` install
already registered in the shared `.venv`, so install the root package first (see Commands)
or `pip` will fail to resolve it against PyPI.

**When adding a new dependency:** install it locally to find the version you need, add it
to `dependencies` (or the `dev` extra) in the relevant `pyproject.toml` (root for
`src/domain`/`src/application`/`src/infrastructure`, `apps/mcp-server/pyproject.toml` for
the app), and
re-run the matching `pip install -e` from Commands. If something you already `import` isn't
declared, add it — arriving transitively via `mcp` or another dep is not declaring it.

## Tests

`tests/test_retrieval.py` (root) imports `application.retrieval.find_sources` directly and
asserts against the returned `Source` dataclasses — no MCP transport in the loop. Keep
following that pattern: **retrieval logic lives in `application/retrieval` precisely so it
can be tested without any transport**, independent of which app (MCP, A2A, ...) calls it.
If `apps/mcp-server`'s `server.py` wrapper (the dataclass → pydantic conversion, tool
registration) grows logic beyond a straight pass-through, add tests for it under
`apps/mcp-server/tests/`, mocking the MCP transport rather than the application layer.

**Prefer equality/membership assertions that would catch a real regression** over vague
truthiness — e.g. `all("forgiveness" in source.concepts for source in results)`, not just
`assert results`. The existing empty-query and no-match tests already encode `find_sources`
returning `[]` as *intentional behavior*, not an oversight — preserve that if you touch the
function.

**The no-`dict` policy (see Typing) applies to test code too.** Don't build expected/actual
values as `dict` literals to compare against a model or dataclass — construct the real
`Source`/`SourceResult` (or whichever type is under test) instead, or assert against its
fields directly. Use a `pydantic.BaseModel` when the test is exercising something at the
MCP wire boundary (`apps/mcp-server/tests/`) and a plain `@dataclass` for domain-layer
fixtures (root `tests/`) — match whichever type the code under test actually returns rather
than introducing a third shape just for the test.

## Architecture

DDD-layered, but still minimal within each layer — there's exactly one domain concept
(`sources`) and one use case (`retrieval`), so don't add sibling packages
(`domain/concepts`, `application/exploration`, `infrastructure/embeddings`, etc.) ahead of
need. Add a new one only once there's a real tool/use case that needs it, per the README's
roadmap (`explore_situation` and friends).

- `apps/mcp-server/src/mind_of_christ_mcp/server.py` — entrypoint only: builds the
  `MCPServer`, registers tools via `@mcp.tool()`, calls into `application/retrieval`, and
  does the wire-shape conversion (dataclass → pydantic model, defined in `schemas.py`) for
  each tool. Stays thin — no retrieval logic here, no domain/infrastructure imports.
- `apps/mcp-server/src/mind_of_christ_mcp/schemas/` — the pydantic `BaseModel`s each tool
  returns, one module per concept (e.g. `schemas/sources.py` → `SourceResult`, imported as
  `from mind_of_christ_mcp.schemas.sources import SourceResult` — `schemas/__init__.py`
  stays empty, see What this is) rather than one file for all of them — mirrors
  `domain/sources/`, `application/retrieval/` splitting by concept instead of by layer.
  This is where a tool's return type lives, never a bare `dict` (see Typing). A new tool
  with its own wire shape gets its own `schemas/<concept>.py`, not a new class appended to
  an existing one.
- `src/domain/sources/models.py` — the `Source` frozen dataclass: the entity itself, no
  behavior, no storage or transport concerns.
- `src/domain/claims/models.py` — the `Claim` frozen dataclass: one assertion a passage
  makes, with evidence offsets into `Source.text`. Subject/object are surface forms (no
  entity resolution yet). Negation lives only in `polarity`, never as a predicate, and
  `attribution` separates what the Course asserts from what it reports the ego or others
  believing — keep both when extending the model.
- `src/application/retrieval/find_sources.py` — the use case: matches a query against
  `infrastructure.database.sources.list_sources()`, deliberately independent of the MCP
  transport so it's unit-testable directly (see Tests). This is where new use cases
  (`explore_situation`, etc.) get their own `src/application/<use_case>/` package.
- `src/application/extraction/extract_claims.py` — the `ClaimExtractor` protocol that a
  provider adapter implements (under `src/infrastructure/llm/`, once one exists), and
  `extract_claims`, which anchors each `CandidateClaim`'s quoted evidence to offsets in
  `Source.text`. Candidates whose quote is missing or ambiguous come back as
  `RejectedCandidate`s instead of being dropped, because the rejection rate measures
  how often a model invents evidence. `anchor_claim` is also what
  `evaluation/claims/gold.py` uses, so gold and predicted claims are anchored
  identically. A source whose response can't be parsed raises `ExtractionFailedError`,
  which is recorded per source. Any other exception, such as a provider outage, stops
  the run.
- `src/application/extraction/prompt.py` — `SYSTEM_PROMPT` (the single statement of the
  labelling rules the gold set follows), `parse_response`, and `PromptedClaimExtractor`,
  which wraps a `Complete` function (`(system, user) -> reply text`). A provider adapter
  implements only `Complete`, so every provider is compared on the same prompt and
  parser. Changing a rule means relabelling the gold set and bumping `PROMPT_VERSION`.
- `src/infrastructure/database/sources.py` — stub in-memory `list_sources()`, explicitly a
  placeholder for a real repository. When a real datastore arrives, it should sit behind
  this same `list_sources`-style signature so `domain/` and `application/` don't need to
  change shape — only what backs them.

**Push work to its natural layer as the app grows**: entities/business rules go in
`domain/`, use-case orchestration in `application/`, concrete storage/external calls in
`infrastructure/`, and wire-shape conversion stays in each app's own thin adapter
(`server.py` for MCP) — never leaked into `application/`'s return types.

## Deployment

None yet — this is a local prototype run over stdio for manual/agent testing. No CI, no
container, no secrets. Document the pipeline here once one exists (see the base template
this file was generated from for the shape: CI on push, container build, orchestrator
secrets, migrations-before-app if a real datastore is added).
