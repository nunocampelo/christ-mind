# Plan: Sources display, canonical ACIM references, and answer precision

## Context

Follow-up to the agent quality work. A reviewer walked through live "mind of God" /
"mind of Christ" answers and the Sources panel and raised several issues; a separate
corpus-pipeline investigation then surfaced a data-correctness problem that reshapes the
reference work. The duplicate-answer bug and fan-out control are already fixed.

This plan covers four "do now" items. One larger behavioral change is deferred to
`mind-mapper-neighborhood-followup.md`; the acim.org `source_url` mapping is deferred to
`acim-source-url-mapping.md`.

### The four "do now" items

1. **Answer precision** — the model wrote "these show the mind of God through what dwells in
   it and *issues from it*"; "issues from it" asserts a directional/causal relation the
   claims (things *dwelling in* the Light) don't state. Tighten the answer prompt.
2. **Sources layout bug** — for longer entries the source chip renders to the *right* of the
   quote instead of *below*. Web-only CSS/markup.
3. **Used vs. retrieved-but-not-used** — split the Sources panel into two labeled groups.
4. **Canonical ACIM reference** — show `T-4.in.1:3` (part-chapter-section-paragraph:sentence)
   / `Matthew 5:7` instead of the slug `t1-1-37`, kept separate from `claim_id`.

### The reference correctness problem (drives #4's shape)

Use ACIM's own canonical annotation (Foundation for Inner Peace: `T-13.VII.9:1` =
part.chapter.section.paragraph:sentence), not an invented scheme. But the corpus can't
faithfully produce it today:

- **Paragraph number is WRONG.** `sources_acim.py` splits each chapter file on blank lines
  and numbers paragraphs 1..N *by position* (`id = f"t{ch}-{sec}-{number}"`, `paragraph =
  number`). The source markdown is a numbered list (`1.`, `2.`, `3.` — verified in
  `data/acim/01/chap0101.md`), and a single canonical item can span multiple blank-line
  blocks (indented continuation lines). So the stored `paragraph` is the Nth blank-line
  block, **not** ACIM canonical paragraph N. Rendering `T-1.I.37` from it would look
  authoritative and point at the wrong passage — worse than the cryptic slug. This is a
  **loader fix**, and it is the root of #4.
- **Section is reliable:** clean contiguous integers per chapter; `0` is always the
  introduction (`0 → in`, `1 → I`, `2 → II`, ...). Confirmed across chapters 1-4.
- **No `:sentence` and no `source_url` are stored.** `:sentence` is *derivable* from the
  claim's `evidence_start`/`evidence_end` offsets into the paragraph text (paragraphs are
  multi-sentence). `source_url` is NOT derivable (acim.org blocks fetch; `/s/79?wid=` ids
  are opaque) — deferred.

## Changes — ordered by dependency

### A. Loader: recover canonical paragraph numbers (data correctness, do FIRST)

`src/infrastructure/database/sources_acim.py` — replace the blank-line split
(`re.split(r"\n\s*\n", body)`) + positional `enumerate` numbering with a parser that reads
the leading list marker (`^\s*(\d+)\.\s`) as the canonical paragraph number, folding
indented continuation lines/blocks into the item they belong to until the next marker. Set
both `id` (`t{ch}-{sec}-{canonical}`) and `paragraph` from that marker.

- **This changes `Source.id` values** for any ACIM paragraph whose positional number
  diverged from its canonical number. `claim.source_id` and the evidence offsets are anchored
  to those ids and to `Source.text`, so the served `corpus.jsonl` (4007 claims, hand-promoted)
  must be checked: if ids or paragraph groupings shift, evidence offsets can fall in the wrong
  paragraph. **Before merging, run a migration/verification pass**: re-resolve every claim's
  evidence against the re-parsed sources (`evidence.py` bounds-check + `source.text.find`)
  and fail loudly on any mismatch, exactly as `evaluation/claims/gold.py` already does when
  text moves. If offsets moved, the corpus must be re-anchored, not silently accepted.
- Because this can shift ids, treat A as its own reviewable step with its own test run,
  even though it lands in the same branch.

### B. Reference formatter (application layer)

New `src/application/retrieval/reference.py` — `source_reference(source, claim) -> str`:
- ACIM: `T-{chapter}.{section_label}.{paragraph}` where `section_label` is `in` for 0 else a
  roman numeral (small local int→roman helper; sections are low integers). Append
  `:{sentence}` (or `:{a}-{b}` when the evidence span crosses sentences) derived by
  sentence-splitting `source.text` and locating `claim.evidence_start`/`evidence_end`.
- Bible: `{book} {chapter}:{verse}`.
- Any shape fitting neither → fall back to `source.id` (display must never break).
- Sentence splitting is heuristic (abbreviations, quoted scripture, former `<br/>` breaks):
  keep a small, tested splitter; test against real ACIM paragraphs (e.g. `t1-0-4`, ~8
  sentences). Lives beside `evidence_text`, which likewise resolves `source_id → Source`
  via `_SOURCES_BY_ID` at the application boundary (`server.py` takes no infra dependency).

### C. Plumb `reference` through the wire (kept separate from `claim_id`)

- `apps/mcp-server/.../schemas/claims.py` — add `reference: str` to `ClaimResult`.
- `apps/mcp-server/.../server.py` `_to_claim_result` — resolve the `Source` (reuse the
  application layer's `_SOURCES_BY_ID` via a small `source_for(claim)` helper) and set
  `reference=source_reference(source, claim)`. Keep `source_id` (internal key).
- `apps/agent/.../application/answer.py` `CitedClaim` — add `reference: str`.
- `apps/agent/.../domain/orchestrator.py` `_to_cited_claim` — carry `reference` from the
  payload, defaulting to `source_id` if absent (graceful degradation).
- `apps/web/src/api/agentApi.ts` — add `reference: string` to `CitedClaim` + `isCitedClaim`.

### D. Sources display (web)

- `apps/web/src/components/chat/CitedAnswer.tsx`:
  - `ClaimEvidence` — wrap gloss + quote + source in one content container so the grid is
    strictly `[ordinal][content-stack]` (fixes the source-to-the-right breakage on long
    quotes). Render `claim.reference` in the `.cited-source` chip, not `claim.source_id`.
  - Partition `sortedClaims` by whether it has an ordinal (already computed) into **cited**
    and **uncited**; render two labeled groups inside the existing `<details>`: "Cited in
    this answer" (numbered, ordinal order) then "Also retrieved" (unnumbered).
- `apps/web/src/components/chat/chat.css` — content wrapper as the single grid child in
  column 2 (`display:flex; flex-direction:column`); give gloss vs. quote clearer
  weight/spacing separation (reviewer noted they read similarly) — no new structure.

### E. Answer precision (agent, prompt-only)

`apps/agent/.../domain/prompt.py` `_EVIDENCE_BOUNDARY` — extend the "narrowest wording" rule:
a claim that X *dwells/lives in* Y does not license "X issues from / flows from / is produced
by Y"; do not add a directional or causal relation the claim doesn't state. Same class as the
existing "God gave them His peace" → "God's nature is peace" example. Honest caveat: reduces,
does not eliminate, per-generation overreach.

## Tests

- `tests/` (root) — loader (A): a chapter file whose canonical numbering diverges from
  positional yields the canonical `paragraph`/`id`; a multi-block item folds into one source.
  Reference (B): `source_reference` for an ACIM section source (`T-1.I.n:k`), a chapter-intro
  (`T-1.in.n`), a cross-sentence span (`:a-b`), a Bible source (`Matthew 5:7`), and an
  unknown shape (falls back to id). Construct real `Source`/`Claim` objects (no-`dict`).
- **Corpus verification (A):** a test that re-resolves every served claim's evidence against
  the re-parsed sources and asserts no offset/text mismatch (guards the migration).
- `apps/mcp-server/tests/test_server.py` — a `find_claims` `ClaimResult` carries a non-empty
  `reference` distinct from the raw slug for a known ACIM claim.
- `apps/agent/tests/` — `_claim_result` fixture + `_to_cited_claim` carry `reference` into
  `last_answer.cited_claims`; `test_prompt.py` asserts the new precision phrase.
- `apps/web/.../CitedAnswer.test.tsx` — reference shown in the chip; cited vs. uncited land in
  the two groups; source renders inside the content stack (structural assertion).

## Verification

```bash
# repo root
.venv/bin/python -m pytest tests apps/mcp-server/tests apps/agent/tests -q
.venv/bin/pyright
cd apps/web && npx vitest run
# live: Sources panel + an answer
.venv/bin/python -m mind_of_christ_agent "can you describe the mind of god?"
```

Success: references read as `T-4.in.1:3` / `Matthew 5:7` and point at the correct passage
(corpus verification green); Sources panel shows two labeled groups with the source below
each quote; the answer avoids asserting a directional relation the claims don't state; all
suites + pyright clean.

## Notes / non-goals / risks

- **Biggest risk is A (loader correctness).** Do not ship the pretty reference on top of
  wrong paragraph numbers. If the migration shows offsets moved, stop and re-anchor the
  corpus before doing B-E — a wrong-but-authoritative reference is worse than the slug.
- `reference` is one resolved string formatted in the application layer, mirroring
  `evidence_text`; the web does not reassemble structured fields.
- Deferred: `source_url` (`acim-source-url-mapping.md`), mapper neighborhood expansion
  (`mind-mapper-neighborhood-followup.md`).
- Bible sentence/line: not applicable (verses are already the citable unit).
