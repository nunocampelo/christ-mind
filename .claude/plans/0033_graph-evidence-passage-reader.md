# Redesign the graph evidence panel as a passage reader

## Context

The graph explorer's right-hand `EvidencePanel` (shipped in plan 0030, with finding #5's
locator fix layered on in plan 0032) is redundant: it prints the relationship as a gloss
sentence, then quotes the extracted clause as a standalone blockquote, then quotes the
*same* clause a third time inside a collapsed "Show in context" that holds the full
passage. The relationship is already visible on the left (relationship list) and in the
canvas, so the gloss and the standalone clause are pure repetition, and the full source
text — the most valuable thing — is hidden behind a click.

Redesign the panel into a **passage reader**: the full source block always visible with the
selected claim's supporting words highlighted, redundant repetition removed, qualifiers and
(for non-projectable claims) a short "not shown in graph" note kept, and the source
reference compact with a "Source details" disclosure for metadata.

This supersedes finding #5's standalone `SourceLocator` layout from plan 0032 — the honesty
requirement (ACIM numbers are import ordinals, not a verified canonical citation) is
preserved, just relocated into the new compact-reference + details structure. No data model,
corpus, or import changes: the artifact's `PassageRef.evidence` already carries
`before + clause + after` (the full block) plus the locator fields, which is everything the
reader needs.

The repo-local copy of this plan is `.claude/plans/0033_graph-evidence-passage-reader.md`
(next number after 0032); keep the two in sync and stage the repo-local one.

## Decisions (confirmed with user)

- **Full passage always visible**, selected clause highlighted in place (`<mark>`). This is
  the current "Show in context" blockquote promoted to the default and only rendering.
- **Remove** the gloss relationship sentence and the standalone clause blockquote.
- **Qualifier chips stay** above the passage (Negated / Conditional / Question / Attributed
  to …), reusing the shared `qualifierLabels` helper and existing `Qualifiers` component.
- **Non-projectable exclusion note** reads **"Not shown in graph: {reason}"** (e.g. "Not
  shown in graph: missing object"), placed just above the passage with the qualifier chips.
  This is graph-mechanics info, deliberately NOT inside "Source details".
- **Compact source reference below the passage**, carrying the ordinal and an inline caveat;
  **"Source details"** disclosure holds *source* metadata only (dataset edition, raw ID):
  - ACIM:
    > A Course in Miracles · Ch 1 · Sec 1 · Block 29
    > (stored location, not a verified citation)
    > ▾ Source details
    >    Dataset edition: "Sparkly Edition" · ID: `t1-1-29`
  - Section 0 renders "Introduction" instead of "Sec 0" (as today).
  - Bible (verse): compact `Matthew 5:7`, a real citation — no caveat, no edition line
    (blank edition); "Source details" shows the raw ID only.
  - Fallback: raw `source_id`, no caveat.
- **"Source details" holds information about the passage's source**, nothing about why a
  claim is or isn't drawn.

## Changes

### `apps/web/src/api/sourceRef.ts` — reshape `graphSourceLocator`

The current `GraphLocator` union was built for the standalone three-line `SourceLocator`.
Reshape it to feed a compact line + details split, keeping the `kind` discriminant:

- `{ kind: "acim"; compact: string; caveat: true; edition: string; id: string }` where
  `compact = "A Course in Miracles · Ch {chapter} · {Sec N | Introduction} · Block {paragraph}"`
  (omit missing parts).
- `{ kind: "verse"; compact: string; id: string }` where `compact = "{book} {chapter}:{verse}"`,
  no caveat, no edition.
- `{ kind: "fallback"; compact: string }` → raw `source_id`.

Keep the `book === "ACIM"` / `book && verse != null` / else branching from plan 0032. Leave
`sourceReferenceParts`/`sourceReference` (the chat citation helpers) untouched.

### `apps/web/src/features/graph/EvidencePanel.tsx` — the reader

Replace the render body (currently lines ~111-153):

- Drop `gloss` and the `graph-evidence-gloss` paragraph.
- Drop the standalone `evidence-clause` blockquote.
- Render the full passage inline, always visible, highlighting the clause:
  `before` + `<mark data-testid="passage-clause">clause</mark>` + `after`, in a single
  `<blockquote data-testid="passage">` — same offset-safe segment concatenation the old
  "Show in context" used (never re-slice on offsets).
- Keep the `Qualifiers` chips above the passage.
- For `kind === "non_projectable"`, render `Not shown in graph: {reason.replace(/_/g," ")}`
  above the passage (reuse `data-testid="exclusion-reason"`, reword from "Not drawn as an
  edge").
- Below the passage: a new `SourceReference` component rendering the compact line, the
  inline `(stored location, not a verified citation)` caveat for ACIM, and a
  `<details data-testid="source-details">` with the edition/ID.
- Replace the old `SourceLocator` component accordingly; keep the no-passage fallback
  (`evidence-missing`) and the empty-selection state unchanged.

### `apps/web/src/features/graph/graph.css`

- Add passage-reader classes: `.graph-reader-passage` (generous line-height, the clause
  `<mark>` styled like the old `.cited-context-clause`), `.graph-reader-ref` (compact,
  muted), `.graph-reader-caveat` (italic, muted), `.graph-reader-details`.
- Stop depending on chat's `.cited-*` classes in the graph panel (the reader is its own
  thing now). Remove the now-unused `.graph-evidence-gloss` rule; keep
  `.graph-evidence-excluded` if the exclusion note reuses it, else fold into a reader class.
- `EvidencePanel.tsx` currently imports `@/components/chat/chat.css` for the `.cited-*`
  classes — drop that import once the reader uses only graph-local classes.

## Tests

Update `apps/web/src/features/graph/GraphPage.test.tsx` (the panel is exercised through the
page; the fixture from plan 0032 already has ACIM passages + a non-projectable atonement
claim):

- **Passage always visible, no redundancy:** after selecting the negated edge, assert the
  passage blockquote is present with the clause in a `<mark>`, the surrounding `before`/
  `after` text is shown, and there is **no** separate gloss sentence and **no** standalone
  `evidence-clause` element (assert those testids are absent). Non-BMP `👁` still survives.
- **Qualifiers still shown:** `qualifiers` contains "Negated" for that edge.
- **Compact ACIM reference + caveat + details:** select the atonement non-projectable claim;
  assert the compact ref reads `A Course in Miracles · Ch 1 · Sec 1 · Block 1`, the caveat
  `(stored location, not a verified citation)` is visible, and `source-details` holds
  `Sparkly Edition` and the raw id — and that "Source details" does NOT contain the
  exclusion reason.
- **Exclusion note placement + wording:** that claim shows `Not shown in graph: missing
  object` above the passage (outside `source-details`).
- Adjust the existing "selects an edge … rendering evidence, qualifiers, and highlight" and
  "labels an ACIM locator…" tests to the new structure (the old `evidence-clause`,
  `evidence-context`, `source-locator`, and `graph-evidence-gloss` expectations change).

No new Python tests — the exporter and artifact are unchanged.

## Verification

```bash
# From apps/web
npx vitest run src/features/graph/     # updated panel + existing graph tests
npx vitest run                         # full frontend suite stays green
npm run build                          # tsc -b + vite build clean
```

Manual spot-check: run the app, open `/graph`, select an edge — the full passage shows
immediately with the supporting words highlighted, no repeated relationship sentence, a
compact reference with the caveat beneath, and edition/ID under "Source details". Select a
non-projectable claim and confirm the "Not shown in graph: …" note sits above the passage.

## Out of scope / explicitly NOT doing

- **Importing a richer ACIM edition** with real paragraph numbers and sentence-level verse
  superscripts (canonical `T-1.VI.1:1–5:10` form). The current corpus is flat prose with
  only section-level refs; genuine verse citations would require new source files, a new
  parser, new `Source` fields, and re-anchoring every claim + re-exporting the projection
  and chat citations. That is a separate, much larger effort — this plan deliberately keeps
  the honest "stored location, not a verified citation" framing precisely because the data
  can't back a canonical citation yet.
- Any change to chat citations or the `Source`/claims/projection data model.
- The large-bundle / lazy-load-the-graph-route perf item (still out of scope).
- Leave the git commit to the user (per no-self-commit).
