# Follow-up: `source_id` is parse-order fragile

## Problem

A source id like `t1-1-64` is `t{chapter}-{section}-{N}`, where **N is the ordinal of the
blank-line-separated block** within the section file, assigned at import time by
`enumerate(paragraphs, start=1)` in `src/infrastructure/database/sources_acim.py:53`.

N is *not* the Course's Principle/verse number. In `01/chap0101.md`, "The emptiness engendered
by fear..." is labelled Principle `42.` in the markdown but lands in **block 64**, because the
loader counts every blank-line block — including sub-paragraphs hanging under one numbered
Principle — so the running block counter drifts ahead of the Principle numbers (102 blocks vs.
50 Principles in that file).

### Why this is a risk

Any edit to a chapter `.md` that adds, removes, or merges a blank-line block **renumbers every
subsequent block**, silently changing their ids and shifting evidence offsets. Nothing errors —
claims just re-anchor to the wrong text.

This is the same fragility the note in `src/domain/claims/identity.py` warns about ("offsets
shift under any harmless edit to the source text"), except it applies to the **`source_id`
itself**, not just the offsets. `identity.py` protects the *claim id* by fingerprinting the
evidence quote; the `source_id` has no such protection.

### Blast radius

Everything keys on `source_id`:
- `src/infrastructure/database/data/claims/corpus.jsonl` — ~4,000 claims
- `evaluation/claims/gold/*.jsonl` — ~190 gold claims
- entity resolutions, chains — all reference claims by `source_id`

A single re-paragraphing of chapter 1 could invalidate all chapter-1 anchors at once, with no
failure surfaced until a claim's evidence quote no longer matches its offsets.

## Options (not yet decided)

1. **Derive the id from the Course's real citation.** Note the standard ACIM citation is
   `T-<chapter>.<section>.<paragraph>:<sentence>`, where paragraph is numbered *by position* —
   i.e. essentially what the current scheme already computes, so it does **not** escape the
   edit-fragility on its own. The `42.`-style numbers I first reached for do **not** generalize:
   a survey of all 26 chapter files shows numbered items appear in only 4 files (chapter 1's 9
   Principles, plus short restarting embedded lists in `02/chap0203`, `02/chap0204`,
   `03/chap0301`); the other 22 files are pure prose with no per-paragraph number. So there is
   no corpus-wide numbered spine to anchor on, and this option reduces to "keep position-based
   ids but make them survive edits" — which is really options 2 and 3.

2. **Store an explicit stable id in the markdown frontmatter / per-paragraph marker** rather
   than computing it from position. Most robust, most authoring overhead.

3. **Guard the current scheme**: add a check (test or `gold.py`-style assertion) that every
   stored `source_id` still resolves and every stored offset range still matches its recorded
   evidence quote, so a re-paragraphing fails loudly in CI instead of silently. Cheapest;
   doesn't fix fragility, just makes breakage visible.

## Recommendation

Short term: option 3 (fail-loud guard) so edits can't silently corrupt anchors. Longer term:
option 2 (an explicit stored id per paragraph, in frontmatter or a marker) is the only one that
truly escapes position-fragility, since the corpus has no numbered spine to derive stable ids
from (see option 1). This aligns with `identity.py`'s "anchor by content, not position"
principle — but for the `source_id` itself rather than just the evidence offsets.

Out of scope for the evidence-quote change (that work is complete and id-scheme-agnostic).
