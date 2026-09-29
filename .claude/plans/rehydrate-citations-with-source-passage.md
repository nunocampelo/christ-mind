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

## The rehydration invariant

After `_rehydrate`, for every cited claim:

```text
evidence_context == source paragraph   when the source exists
evidence_context == ""                 only when source lookup failed/missing
```

No attempt is made to infer whether context is *needed* — that keeps it universal.

**Coordinate system (load-bearing):** `evidence_start`/`evidence_end` are offsets into
`evidence_context` (the paragraph), NOT into the `evidence` field (the clause). Once the DTO
leaves the orchestrator there are two strings; the frontend needs one unambiguous coordinate
system, and it is the paragraph, because that is what `ClaimResult`'s offsets already index
(`Source.text`). So the invariant, when a source is present, is:

```text
evidence_context[evidence_start:evidence_end] == evidence
```

**On mismatch (source present but the slice != evidence): raise, fail loud.** This is the
source-version-drift / extraction-bug signal — the same stance as `evaluation/claims/gold.py`
("fail loudly if the text moved") and CLAUDE.md's fail-loud-over-default-silently rule. Never
silently "fix" the offsets and never ship a misaligned citation. Raise a domain-specific error
with a static message (no interpolation of source/claim text, per CLAUDE.md error handling).
The check is gated on `evidence_context` being non-empty — a missing source (`""`) is benign
and skips validation.

## Changes

### 1. `CitedClaim` — carry the passage and the offsets
`apps/agent/src/mind_of_christ_agent/application/answer.py`
- Add `evidence_context: str = ""` — the full source paragraph (`SourceResult.text`).
- Add `evidence_start: int = 0`, `evidence_end: int = 0` — currently in `ClaimResult` but
  dropped in `_to_cited_claim`. **Offsets into `evidence_context`, not into `evidence`** —
  state this in a short field comment so the coordinate system survives the DTO boundary.
- Defaults keep it backward-compatible if a claim's source can't be fetched.

### 2. `_to_cited_claim` — stop dropping the offsets
`apps/agent/src/mind_of_christ_agent/domain/orchestrator.py`
- Read `evidence_start` / `evidence_end` from the MCP dict into the new fields. Still
  dict-only; no `Source` access here.

### 3. Orchestrator — batch-rehydrate after each retrieval
`apps/agent/src/mind_of_christ_agent/domain/orchestrator.py`
- A pure helper that returns a **new list** (no mutation of an externally held collection;
  `CitedClaim` is frozen anyway):

  ```python
  async def _rehydrate(
      claims: list[CitedClaim], mcp_client: MCPClient
  ) -> list[CitedClaim]:
      source_ids = {c.source_id for c in claims if not c.evidence_context}
      if not source_ids:
          return claims                      # idempotent: nothing left to fetch
      sources = await get_sources(mcp_client, list(source_ids))
      by_id = {s.source_id: s.text for s in sources}
      out = []
      for c in claims:
          if c.evidence_context:
              out.append(c); continue
          ctx = by_id.get(c.source_id, "")
          if ctx and ctx[c.evidence_start:c.evidence_end] != c.evidence:
              raise CitationRehydrationError  # static message; see invariant
          out.append(c.model_copy(update={"evidence_context": ctx}))
      return out
  ```
- Call it right after each `_absorb` (both call sites: initial `find_claims` batch and the
  reactive loop), reassigning: `cited_claims = await _rehydrate(cited_claims, self._mcp_client)`.
- Rehydrates only claims lacking context → one `get_sources` call, deduped by `source_id`
  (many claims share `t2-1-7`), and naturally idempotent across steps.

### 4. Passage-grouped rendering — on BOTH answer paths
`apps/agent/src/mind_of_christ_agent/domain/prompt.py` + `.../domain/orchestrator.py`

**Design correction found during implementation:** `answer_user_prompt` is NOT the primary
answer prompt — it is only the max-steps-**exhaustion fallback**. On the common path the
model emits `{"final"}` straight from `decision_user_prompt`, whose `observations` show
claims as the raw `find_claims` JSON (evidence clause, no paragraph). So rendering only in
`answer_user_prompt` would leave the motivating "my kind" failure unfixed on the common path.

Fix: `render_cited_claims` (public) is the single citation renderer, used by **both**:
- `answer_user_prompt` (fallback), and
- the orchestrator's `_claim_observation`, which rebuilds each cited tool's `observations`
  entry from the freshly-rehydrated `CitedClaim`s (`cited_claims[before:]`) instead of
  `_result_text`. Non-cited tools (`chain_claims`) keep the raw tool text.

Rendering: group cited claims by `source_id`; render each **paragraph once**, then the
claims extracted from it beneath — the same semantic unit a human reader gets:

  ```text
  PASSAGE [t2-1-7]
  "This is the PROPER use of denial... You can do ANYTHING I ask. I have asked you to
   perform miracles..."
  CLAIMS WITHIN PASSAGE:
  - claim_id=95eaa50303ea9c1b [NEGATED?] evidence: "The miracle worker is one who accepts
    my kind of denial and projection"
  - claim_id=... evidence: "..."
  ```
- Retain the authoritative-evidence rule almost verbatim: *the evidence span is
  authoritative for the claim; the surrounding passage resolves references like "my kind",
  it does NOT license broadening the claim or reversing its polarity.* Especially important
  for `NEGATED` handling — preserve the existing polarity marking.

### 5. Webapp — clause-in-context rendering
Evidence-artifact consumer (frontend; see `frontend-chat-plan-port` memory).
- Render the evidence clause as the quote; make the paragraph (`evidence_context`)
  expandable, with the clause highlighted inside via `evidence_start/evidence_end`.
- No wire change beyond the enriched `CitedClaim` — `AgentAnswer.model_dump_json()` carries
  the new fields automatically.
- Scope note: the frontend location per the current roadmap may not be in this repo yet;
  if so, land 1–4 (server side) and track the webapp render as the immediate follow-up.

## Tests
`apps/agent/tests/` (mock MCP transport):
- **Invariant:** a resolved claim gets `evidence_context` == the source paragraph, and
  `evidence_context[evidence_start:evidence_end] == evidence`.
- **Batching/dedupe:** claims sharing one `source_id` trigger a single `get_sources` call.
- **Missing source:** `evidence_context == ""`, no raise, still renders.
- **Drift fails loud:** a source whose text no longer anchors the offsets raises
  `CitationRehydrationError` (present-source mismatch), not a silent repair.
- **Idempotent:** re-running `_rehydrate` on already-hydrated claims issues no `get_sources`
  call and returns them unchanged.
- **Regression for the motivating case (`95eaa50303ea9c1b`):** after rehydration, the
  rendered prompt contains the surrounding text that resolves "my kind" (e.g. the paragraph's
  "PROPER use of denial" / "I have asked you to perform miracles"), so the antecedent is
  present without the model having to infer it from the bare claim. This is the concrete
  failure the increment exists to fix, not just plumbing.
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
