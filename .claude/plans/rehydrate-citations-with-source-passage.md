# Rehydrate citations with their source passage

## Problem

A claim is a normalized retrieval unit, not a self-contained quotation. Some claims
(`95eaa50303ea9c1b`: "The miracle worker is one who accepts my kind of denial and
projection") carry anaphoric/deictic references — "my", "my kind" — whose meaning lives in
the surrounding paragraph, not in the triple or the evidence clause. `attribution=course`
flags the voice but does not resolve the antecedent.

Today both consumers of a citation strand on the bare evidence clause:

- the **answer LLM** — `_render_cited_claim` in `apps/agent/.../domain/prompt.py` shows
  `subject verb object -- evidence: "<clause>"`, so the model synthesizes from a
  proposition whose "my kind" has no antecedent in the prompt (hallucination risk).
- the **webapp** — the `evidence` A2A artifact is `AgentAnswer.model_dump_json()`, driven
  by the same `CitedClaim` fields, so it displays the same stranded clause.

## Contract

**Claims are retrieval units, not presentation units.** Before a claim is used as evidence
(prompt or webapp), it is rehydrated to its source paragraph. This is universal — no
per-claim "needs-context" flag, no classifier (that would be a droppable rider field, the
same failure shape as polarity at the DTO boundary). The rehydration unit is the paragraph,
which `Source`/`SourceResult` already stores at exactly the right granularity
(`t2-1-7` = ch2/§1/¶7; the paragraph itself establishes "my kind of denial").

The rehydrated passage lives on **one DTO — `CitedClaim`** — so both the prompt and the
webapp inherit it with no per-consumer rehydration logic.

## Decisions (settled)

- **Join site: orchestrator batch `get_sources`.** `find_claims` stays lean; the
  paragraph is joined one level up where the MCP client lives. The `get_sources(source_ids)`
  MCP tool + `application/retrieval/get_source.py` already exist — nothing new to build for
  the fetch.
- **Webapp: clause + expandable context.** The evidence clause stays the highlighted quote;
  the full paragraph is available as context with the clause marked inside it via
  `evidence_start/evidence_end`. Not full-paragraph-as-quote (buries which sentence),
  not clause-only (today's bug).

## Changes

### 1. `CitedClaim` — carry the passage and the offsets
`apps/agent/src/mind_of_christ_agent/application/answer.py`
- Add `evidence_context: str = ""` — the full source paragraph (`SourceResult.text`).
- Add `evidence_start: int = 0`, `evidence_end: int = 0` — currently in `ClaimResult` but
  dropped in `_to_cited_claim`; needed to mark the clause within the paragraph (prompt +
  webapp).
- Defaults keep it backward-compatible if a claim's source can't be fetched.

### 2. `_to_cited_claim` — stop dropping the offsets
`apps/agent/src/mind_of_christ_agent/domain/orchestrator.py`
- Read `evidence_start` / `evidence_end` from the MCP dict into the new fields. Still
  dict-only; no `Source` access here.

### 3. Orchestrator — batch-rehydrate after each retrieval
`apps/agent/src/mind_of_christ_agent/domain/orchestrator.py`
- After `_absorb` adds claims (both call sites: the initial `find_claims` batch and the
  reactive loop), collect the distinct `source_id`s of claims still missing
  `evidence_context`, call the `get_sources` MCP tool **once** for that batch, and fill
  `evidence_context` per claim by matching `source_id` → `SourceResult.text`.
- Implement as one helper (e.g. `_rehydrate(cited_claims, mcp_client)`) called right after
  each `_absorb`, or fold into `_absorb`'s follow-up. Dedupe by `source_id` — many claims
  share `t2-1-7`, so one fetch covers all of them.
- Since `CitedClaim` is frozen, rehydration rebuilds entries via `model_copy(update=...)`.

### 4. `_render_cited_claim` — passage once, claims as pointers
`apps/agent/src/mind_of_christ_agent/domain/prompt.py`
- Group cited claims by `source_id`; render each **paragraph once**, then list its claims
  beneath as clause pointers (claim_id + the evidence clause / offsets). Keeps the prompt
  literally "passages, then claims-within-passages" and avoids repeating a shared paragraph
  N times.
- Preserve the existing polarity/NEGATED handling and the "evidence span is authoritative"
  guidance.

### 5. Webapp — clause-in-context rendering
Evidence-artifact consumer (frontend; see `frontend-chat-plan-port` memory).
- Render the evidence clause as the quote; make the paragraph (`evidence_context`)
  expandable, with the clause highlighted inside via `evidence_start/evidence_end`.
- No wire change beyond the enriched `CitedClaim` — `AgentAnswer.model_dump_json()` carries
  the new fields automatically.
- Scope note: the frontend location per the current roadmap may not be in this repo yet;
  if so, land 1–4 (server side) and track the webapp render as the immediate follow-up.

## Tests
- `apps/agent/tests/` (mock MCP transport): a claim whose `source_id` resolves gets
  `evidence_context` == the source paragraph; the clause at `[evidence_start:evidence_end]`
  equals `evidence`. A batch of claims sharing one `source_id` triggers a single
  `get_sources` call. A claim whose source is missing keeps `evidence_context == ""` and
  still renders.
- Prompt test: two claims sharing a `source_id` render the paragraph once, both claim_ids
  beneath it.
- Preserve the existing citation-diagnostics / polarity behavior (no regression).

## Non-goals
- No extractor/labelling-rule change; the claim is correct, so `PROMPT_VERSION` unchanged.
- No `Source` model change; granularity is already paragraph-level.
- No `find_claims` schema change; it stays lean (join is in the orchestrator).
- No "needs-context" flag/classifier on claims.

## Verify
- `.venv/bin/python -m pytest tests apps/agent/tests -q`
- `.venv/bin/pyright`
