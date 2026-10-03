# Fix the five graph-explorer review findings

## Context

The graph explorer landed over the last two commits (`6bd5506 added graph model`,
`d83dbec add graph page`). A code+corpus review found five defects, all verified against
the committed code and `apps/web/public/graph/projection.json`:

1. **[P1]** Relationship list / canvas omit mode & attribution — conditional/question/
   attributed claims read as flat Course assertions until selected.
2. **[P1]** Canvas edge selection breaks after navigating to another neighborhood (stale
   closure captured in a mount-only effect).
3. **[P1]** Predicate filter options are derived from the already-filtered, capped edges,
   so selecting one predicate hides the rest, and a node whose first 20 edges share one
   predicate only ever offers that one filter.
4. **[P2]** 94 non-projectable claims are unreachable: their endpoint concepts are never
   registered as nodes, so they can't be searched or surfaced.
5. **[P2]** The evidence panel reuses the chat citation formatter, presenting ACIM import
   block ordinals as canonical Chapter/Section/Paragraph citations and dropping edition.

Intended outcome: every claim's qualifiers are visible before selection, canvas selection
survives navigation, filters expose the full predicate set, every claim **with at least
one usable endpoint** is reachable, and ACIM locators are honestly labelled as stored
import ordinals. (Claims with *no* usable endpoint — blank subject *and* blank/missing
object — have nothing to anchor a node to and need a separate browsing path; out of scope,
see below.)

## Decisions (confirmed with user)

- **Point 1 UI:** compact inline suffix in muted text, always visible, following the claim.
  Dot-separated, e.g. `forgiveness is empty gesture · Conditional`,
  `God … · Question · Attributed to ego`. Omit default `assertion` mode and `course`
  attribution. Include `Negated` explicitly. Same wording in the evidence panel (chips stay
  there). Canvas on-edge label stays `verb_phrase` only (rotated canvas labels can't carry
  qualifier text legibly; list + panel carry them).
- **Point 5 UI:** stored-location label + dataset edition + raw ID + disclaimer:
  > **A Course in Miracles**
  > Stored location: Chapter 1 · Section 1 · Block 22
  > Dataset edition: "Sparkly Edition" · ID: `t1-1-22`
  > Not a verified canonical citation.

  "Block" (not "Paragraph"), "Dataset edition" (not a bare edition label). Bible refs keep
  the plain `Matthew 5:7` form (real verse citations); the stored-location/disclaimer
  treatment is ACIM-only.

## Changes

### Point 1 — qualifier label helper + inline suffixes

- New shared helper module `apps/web/src/features/graph/qualifiers.ts`:
  - `qualifierLabels(polarity, mode, attribution): string[]` returning the non-default
    labels in order `[Negated?, Mode?, Attribution?]`: `Negated` when `polarity ===
    "negated"`; mode capitalized unless `assertion`; `Attributed to <a>` unless `course`.
    This is the single source of truth for the wording, reused by list and panel.
- `RelationshipList.tsx`: replace `edgeText`'s `(negated)` handling with the base
  `subject verb_phrase object` text, then append ` · ` + `qualifierLabels(...).join(" · ")`
  when non-empty, in a muted `<span className="graph-rel-qualifiers">`. Apply the same to
  the non-projectable `<li>` branch (lines 89-93 region).
- `EvidencePanel.tsx`: delete the local `polarityLabel`/`modeLabel`/`attributionLabel` and
  have the `Qualifiers` chip component build its chips from `qualifierLabels(...)` so the
  wording can't drift from the list.
- `graph.css`: add `.graph-rel-qualifiers` (muted, smaller) mirroring the existing
  `.graph-rel-reason` muted style.

### Point 2 — keep the canvas tap handler bound to the current callback

- `GraphCanvas.tsx`: add a `onSelectEdgeRef = useRef(onSelectEdge)` kept current with a
  tiny effect (`useEffect(() => { onSelectEdgeRef.current = onSelectEdge; })`), and change
  the mount handler at line 182 to `cy.on("tap", "edge", (evt) =>
  onSelectEdgeRef.current(evt.target.id()))`. The mount-once effect stays mount-once; only
  the invoked callback is now always the latest. No behavior change to the stable path.

### Point 3 — derive predicate options from the full eligible set, pre-filter/pre-cap

- `graphModel.ts`: expose the full eligible predicate set on the `Neighborhood`. Add
  `allPredicates: Predicate[]` to the `Neighborhood` interface, computed from the
  deduped `[...outgoing, ...incoming]` (the same set that feeds `totalEligible`, line 131),
  **before** `matchesFilters` and the cap, sorted. This keeps the derivation in the pure
  view model (tested directly) rather than in the page.
- `GraphPage.tsx`: replace `availablePredicates` (lines 134-137) with `view.allPredicates`.

### Point 4 — register node endpoints for non-projectable claims too

- `build_projection.py`: register a claim's non-empty surface forms as nodes regardless of
  whether the claim is drawable, so a concept appearing only in non-projectable claims
  still gets a `ProjectionNode` (searchable; its claims surface in the neighborhood via
  `nonProjectableBySurface`). Concretely, in the loop (lines 119-142): call
  `register(subject)` for any non-empty subject, and `register(object)` for any non-empty
  object, before/independent of the drawable decision — the edge is still appended only
  when both endpoints exist. Non-projectable records are unchanged; only the node set
  grows. Determinism (nodes sorted by `node_id`) is preserved.
- This is purely additive to `nodes`; `edges`/`non_projectable`/counts logic is unchanged
  except `CoverageCounts.nodes` (and catalogued/uncatalogued/merged) will reflect the new
  nodes — those counts are computed from `projection.nodes`, so they update automatically.
- Regenerate the committed artifact (see Verification). This changes `content_hash` and
  grows `nodes`; expected: the 94 previously-unreachable claims become reachable.

### Point 5 — ACIM stored-location locator, edition-labelled, with disclaimer

- New helper in `apps/web/src/api/sourceRef.ts` (or a small graph-local module if we want
  to avoid touching the chat helper — prefer `sourceRef.ts` since the ACIM field semantics
  live there): `graphSourceLocator(passage)` returning a **discriminated union on `kind`**,
  never a boolean — a boolean can't tell ACIM from an unknown-source fallback, and a
  populated verse doesn't establish canonical validity:
  - `{ kind: "acim"; title: "A Course in Miracles"; storedLocation; edition; id }` when
    `book === "ACIM"`: `storedLocation = "Chapter {chapter} · Section {section} · Block
    {paragraph}"` (omit missing parts; section 0 → "Introduction" as today), `edition =
    passage.edition`, `id = passage.source_id`.
  - `{ kind: "verse"; title; location }` only when **both `book` and `verse != null`**
    (the existing `Matthew 5:7` form). Field is `location`, not `storedLocation`. No
    edition/disclaimer line.
  - `{ kind: "fallback"; title: source_id }` otherwise.
- `EvidencePanel.tsx`: replace the `referenceParts`/`cited-source` block (lines 23-31,
  130-135) with a `switch` on the locator `kind`: `acim` renders title, "Stored location:
  …", "Dataset edition: "…" · ID: `…`", and "Not a verified canonical citation."; `verse`
  renders plain title + location; `fallback` renders the raw id. New
  `.graph-evidence-locator*` CSS classes rather than reusing `.cited-source`.
- Leave `sourceReferenceParts`/`sourceReference` (chat citations) untouched.

## Tests

- `graphModel.test.ts`: add a case asserting `allPredicates` returns every eligible
  predicate even when a filter is active and even when the first `cap` edges all share one
  predicate (the "God" scenario in miniature using the fixture).
- **`GraphCanvas` test is the REQUIRED point-2 regression test** (a page test that invokes
  the latest mocked callback would pass *with* the stale-closure bug, so it can't be the
  gate). Stub Cytoscape so `cy.on("tap", "edge", handler)` captures the registered handler;
  render `GraphCanvas` with callback A, rerender with a new callback B, then fire the
  captured tap handler and assert **only B** receives the edge id (A is not called). This
  fails against the current mount-only binding and passes once the ref indirection lands.
  Optionally also add a page-level navigation smoke test, but it does not replace this one.
- `RelationshipList`: add/extend a test asserting a conditional + ego claim renders
  `· Conditional · Attributed to ego` and an assertion/course claim renders no suffix.
- `EvidencePanel`: assert ACIM selection renders "Block", "Dataset edition", the raw id,
  and the "Not a verified canonical citation." line, and that a Bible (`verse`) selection
  renders none of them.
- **Frontend reachability flow (point 4), beyond node registration.** Add a `fixture.ts`
  node whose only claim is non-projectable (reachable via its surface form, no drawable
  edge). Test: search for it → select it → assert the `graph-no-relationships` message →
  select the non-projectable claim in the list → assert the evidence panel shows its
  evidence. This proves the claim is actually reachable through the product, not merely
  that a node exists.
- `tests/test_projection.py`:
  - A concept appearing only in a non-projectable claim (claim with `object = None`) has
    its **subject** registered as a `ProjectionNode`.
  - A claim with a **blank subject but a valid object** registers the **object** node
    (confirms endpoint registration is per-endpoint, not all-or-nothing).
  - Keep the existing determinism/coverage assertions.

## Verification

```bash
# Frontend (from apps/web)
npm run test            # 172+ existing tests + the new ones
npm run build           # production build still succeeds

# Python (from repo root)
.venv/bin/python -m pytest tests/test_projection.py -q
.venv/bin/pyright

# Regenerate the committed artifact (point 4) and sanity-check reachability
.venv/bin/python -m application.projection.export_cli \
    --out apps/web/public/graph/projection.json
# The coverage report's node count should rise; the 94 unreachable claims should drop to 0.
```

Manual spot-check in the browser (not required to pass, but confirms points 1/5 visually):
run the app, open `/graph`, search a dense concept (e.g. "God"), confirm every predicate
appears as a filter, qualifiers show inline before selecting, canvas clicks work after
"Explore …", and an ACIM evidence panel shows the stored-location/edition/disclaimer block.

## Out of scope

- The large-bundle / lazy-load-the-graph-route suggestion from the review footer (separate
  perf change, not a correctness fix).
- A browsing path for claims with **neither** a usable subject nor object — nothing anchors
  a node, so endpoint registration can't reach them; they'd need an excluded-claims list.
  Registering all non-empty endpoints already covers every claim with ≥1 usable endpoint,
  which is the scope of "reachable" here and drops the 94 figure to 0.
- Leave the git commit to the user (per no-self-commit).
