# Source-backed graph explorer: dedicated frontend page

## Objective

Add a read-only `/graph` page to the existing frontend so a person can explore
relationships in the available ACIM corpus and inspect the exact evidence behind each
connection. First success means discovering and verifying a meaningful relationship;
agent retrieval and answer quality are separate outcomes for a later increment.

> The graph is a navigable view of extracted, source-backed claims. Every displayed
> relationship must let the reader inspect exactly what the Course says.

Use Python to construct a deterministic projection, existing file-backed data for
storage, and Cytoscape.js in the existing React/TypeScript/Vite app. Build the projection
over the available corpus, but display bounded neighborhoods. Forgiveness,
right-mindedness, and God are inspection cases, not hard-coded export boundaries.

## Existing implementation to reuse

- `src/domain/claims/models.py`: claims already preserve subject, object, normalized
  predicate, original verb phrase, polarity, mode, attribution, and evidence offsets.
- `src/domain/entities/models.py`: entities are sets of observed expressions. IDs are
  fingerprints of those sets; adding an alias changes the ID. Labels are presentation
  choices, not canonical names or evidence of conceptual equivalence.
- `src/infrastructure/database/claims.py` and `resolutions.py`: promoted JSONL claims
  and lexical-baseline entity resolution. Preserve the source datasets.
- `src/application/retrieval/describe_entity.py`: one-hop entity participation and
  aspect-aware ranking. The implementation inspected scans claims, rather than using
  a separate adjacency index. Inspect related retrieval code before introducing one.
- `src/application/synthesis/chain_claims.py`: distinguishes traversed claim paths
  from stored assertions. The explorer must preserve that distinction.
- `apps/web/src/components/chat/CitedAnswer.tsx`: quoted clause, expandable paragraph,
  and evidence highlighting. Extract reusable presentation where appropriate without
  coupling graph evidence to a conversation turn or citation ordinal.
- `apps/web/src/main.tsx`: current routes are `/` and `/c/:conversationId`, both
  rendering `App`. `App` owns the sidebar and the `useConversations` fetch. Register
  `/graph` alongside them and provide navigation between chat and graph (see the sidebar
  Explore section below).
- `apps/web/src/components/chat/Sidebar.tsx`: the route-driven sidebar (`New chat` link,
  then a `Recents` section of conversation rows). Active state is `data-active` plus a
  `bg-muted` highlight. This is the one piece of chrome shared between chat and graph.

Earlier graph retrieval experiments motivate inspecting relationships independently
of agent tool selection. Do not treat their outcomes as proof that this explorer will
improve answers. Confirm current routing behavior before making claims about it.

## Meaning and projection rules

Claims and source passages remain authoritative. Display edges and adjacency indexes
are derived artifacts that can be rebuilt.

| Element | Representation in this increment |
| --- | --- |
| Entity | Existing entity ID, deterministic display label, observed expressions |
| Claim | Existing claim and evidence, preserving all semantic fields |
| Entity occurrence | Derived claim ID + subject/object role + original expression + resolution/eligibility status |
| Source passage | Existing source ID, book/edition/location, paragraph text, evidence span |
| Display edge | Claim ID, endpoint IDs, predicate, original wording, polarity, mode, attribution |

Do not introduce new persistent domain schemas merely to mirror this table. Add typed
projection records at the layer that needs them; follow the existing domain/application/
infrastructure split and keep package initializers empty.

Semantic requirements:

1. Keep related entities distinct, including God, God's Thoughts, and God's Miracles.
   An `is` claim establishes neither identity nor symmetry nor transitivity.
2. Start with one directed edge per eligible claim. Retain parallel edges and self-loops
   if present. Repeated claims are not silently merged; aggregation is deferred.
3. A catalogued lexical entity is not automatically a validated concept. Specify
   endpoint eligibility after inspecting the data. Do not infer a concept by stripping
   qualifications, guessing pronoun referents, or merging related expressions.
4. Keep non-projectable claims inspectable in the relationship list when they involve
   the selected entity. Show their original expressions and the exclusion reason;
   do not manufacture endpoint nodes.
5. Preserve complete subject/object wording and verb phrase. Qualifiers are currently
   embedded in wording and context, not reliably represented as structured fields.
   Show polarity, attribution, and non-assertion mode on the edge/list before selection,
   rather than burying them in the evidence panel. Use text as well as visual styling.
6. Normalized predicate controls filtering; original wording conveys meaning. Review
   labels for reversed normalization such as `arises from` becoming `causes`; display
   a coherent directed relationship without reversing the original quote.
7. A traversable path does not establish a new proposition. Do not add shortcut edges,
   inferred claims, automatic chains, or theological equivalences.
8. Preserve edition and corpus identity. Use the locator scheme actually held by the
   source, and distinguish stored paragraph positions from verified canonical numbering.

Mechanical resolution, concept eligibility, and unresolved contextual meaning are
different statuses. Report only what an automated check can establish; contextual
ambiguity and semantic fidelity require a recorded manual sample review.

## Export contract and delivery

Export a versioned JSON artifact containing metadata, searchable entities, eligible
edges, inspectable claims, supporting passages, and coverage counts. Build subject and
object adjacency indexes once from the projection, including claims that cannot be
drawn as concept-to-concept edges. Construct indexes in the browser from the artifact
if that avoids duplicating the same data in JSON.

Metadata must identify the projection/schema version and content hashes of the claim
file, resolution file, and source texts with their edition/location metadata. Carry
available run IDs, but do not invent a corpus run ID if absent. Include eligibility
rules/version and deterministic ordering. An optional generation timestamp belongs
outside the byte-stable payload.

Use the claim ID as the display edge identity. Sort records deterministically and
select labels deterministically from existing expressions. Snapshot identity scopes
entity IDs and any saved selection; detect incompatible snapshots rather than
silently treating changed IDs as persistent concepts.

Join `claim.source_id` to `Source.id` in a lookup built from
`infrastructure.database.sources.list_sources()`, which aggregates the ACIM and Bible
repositories. Validate source-ID uniqueness, every claim-to-passage join, bounds, and
quoted evidence before export. Missing source IDs, duplicate source IDs, or invalid
evidence fail generation with actionable diagnostics; never silently drop such claims.
Semantic exclusions are accounted for separately, not disguised as integrity errors.

Evidence offsets originate in Python character coordinates. JavaScript string slicing
uses UTF-16 code units: either export validated before/clause/after segments or perform
an explicit coordinate conversion. Test an astral Unicode character preceding the
clause so frontend highlighting cannot drift silently.

For this increment, generate a static artifact under the frontend's public assets and
load it with a typed, validated frontend adapter. Document its generation command and
regeneration workflow. Check artifact size and loading time before committing to one
file; split evidence into static chunks only if measured size warrants it. The page
must work without invoking the chat agent or adding an API service.

## Dedicated `/graph` page

Provide an independent route reachable from the existing sidebar. Reuse visual
conventions and theme; avoid mounting chat hooks or fetching conversation history just
to view the graph.

**Sidebar and shell.** The sidebar stays available on `/graph` so a reader can move
between exploration and conversations. Add an **Explore** section near the top of the
sidebar, above the `Recents` conversation history, holding a single **Course graph**
link to `/graph`. The link shows the active state when `/graph` is open, using the same
`data-active`/`bg-muted` convention as a selected conversation row.

Keeping the sidebar on both routes means lifting it out of `App` into a layout route
(a shell rendering the `Sidebar` once plus an `<Outlet/>`) that wraps the chat routes
and `/graph`. The `useConversations` fetch stays with the shell so `Recents` still
populates, but the graph page must not depend on it or on any chat hook — an empty or
still-loading conversation list must never block or error the graph. If this refactor
is larger than a thin lift, keep the graph page self-contained and record the extra
work rather than coupling the graph to chat state to save effort.

- **Search:** index eligible entities from the resolution catalog by their labels and
  observed expressions, not `Source.concepts` tags. Show distinct matches separately;
  offer inspection cases as starting points only when they map to eligible catalog IDs.
  "No match" means no eligible entity matched in this projection snapshot, not that
  the source corpus has no passage about the query.
- **Canvas:** selected entity and one-hop neighbors, incoming/outgoing arrows, readable
  relationship labels, and visible semantic qualifiers. Preserve selected identity and
  support parallel edges without silently collapsing evidence.
- **Relationship list:** the same visible connections in readable text, plus a clearly
  separated list of participating claims that cannot be drawn. Keyboard selection
  opens the same evidence panel as selecting an edge.
- **Evidence panel:** original claim wording and semantic fields, exact quoted clause,
  source reference and edition, expandable paragraph with the clause highlighted.
- **Controls:** direction and predicate filters, expand a selected neighbor, previous
  view, reset, and an explicit way to reveal more relationships.
- **Counts:** show displayed/available relationships after filtering, hidden eligible
  relationships, and claims excluded from drawing. Changing filters recalculates counts;
  an empty result must not imply the corpus contains no knowledge about the concept.
- **States:** loading, invalid/unavailable artifact, no search match, no eligible
  relationships, and small-screen layout. The relationship list remains usable when
  the canvas is crowded or inaccessible.

Default to at most 20 eligible relationships per neighborhood with deterministic
ordering. Expansion adds a bounded neighborhood, retains existing positions where
practical, and does not rerun the layout over the whole canvas on every selection.
Define a total visible-graph cap and explain truncation before enabling expansion.
Previous/reset restore view state, including filters and selected evidence where valid.

## Reviewable increments

### A. Inspect and specify

Inspect current retrieval/resolution behavior and representative claims for forgiveness,
right-mindedness, and God. Record exact entity IDs and claim IDs scoped to the snapshot,
including definitions, incoming/outgoing claims, negation, attribution, conditional
wording, qualified endpoints, pronouns, and missing objects.

Confirm whether each inspection case resolves to actual baseline catalog entity IDs,
including singleton entities; a case need not belong to a merged group. Record absent,
ambiguous, or ineligible matches as findings rather than blocking the increment or
inventing an entity to make a starting point work.

The inspection report must name these decisions explicitly:

- **Locator rendering by book/edition:** inventory populated fields and document the
  exact display policy for Bible `book/chapter/verse` and ACIM
  `chapter/section/paragraph`, including section 0, unknown editions, missing fields,
  and source-ID fallback. `chapter` is required on `Source`; verse, section, and
  paragraph are optional. The current ACIM loader assigns `Sparkly Edition` and
  positional paragraph numbers; do not present those as verified canonical citations.
  The Bible stub has blank edition fields and some source IDs encode verse ranges
  that the single `verse` field does not capture. Do not infer ranges or edition labels
  from undocumented conventions; record what can be rendered faithfully.
- **Claim-to-passage join:** specify the `claim.source_id` -> `Source.id` lookup from
  aggregated `list_sources()`, source-ID uniqueness, and generation-failure behavior
  for missing references. Include representative evidence-anchor checks.
- **Search vocabulary and eligibility:** index the resolution catalog's observed
  expressions and deterministic labels after explicit eligibility decisions.
  `Source.concepts` are passage tags, not entity aliases, and do not populate graph
  search or create nodes. Define matching/normalization and distinguish no eligible
  search match from an entity with no drawable relationships.

Deliver a short inspection report and finalized projection contract: eligibility rules,
label policy, edge wording, exclusion reasons, neighborhood ordering/caps, and evidence
format. Decide whether the existing entity catalog permits a useful initial concept
explorer without inventing resolution rules. Any curated eligibility decisions must
be explicit and versioned; never hide omissions.

Acceptance: each representative case is either faithfully representable or explicitly
classified as non-projectable, with the original claim still available for inspection.

### B. Deterministic projection

Implement typed projection construction in the shared application layer and a thin
export command using existing repositories. Add an index only where needed and keep
the projection independent of Cytoscape's wire format. Build the passage lookup from
aggregated `list_sources()` and enforce the join and failure rules specified in A.
Generate the artifact and a
coverage report: input claims/entities, drawable claims, non-projectable claims by
reason, endpoint resolution/eligibility counts, and evidence integrity results.

Acceptance: every edge resolves to a claim and passage; all input claims are accounted
for; repeated exports from the same snapshots are byte-identical; semantic fields are
preserved. Report reason counts without double-counting the overall exclusion total.

### C. Read-only explorer

Install and pin a compatible Cytoscape.js version and any required TypeScript typings
using the frontend's existing dependency workflow. Lift the sidebar into a shared
layout route, add the Explore section with the active-highlighted `Course graph` link,
then add `/graph`, the typed artifact loader, bounded neighborhood state, canvas,
relationship list, and shared evidence presentation. Start with a built-in layout; add
a layout extension only if review demonstrates a need.

Acceptance: search and inspect all three cases, follow incoming and outgoing edges,
expand/back/reset, select evidence from canvas or list, and see accurate limits and
qualifiers. The sidebar is present on both chat and `/graph`; the `Course graph` link is
active-highlighted only on `/graph` and a conversation row only on its own route; the
graph page renders with an empty or still-loading conversation list. Existing chat
navigation and evidence presentation continue to work.

### D. Evaluate and decide

Record a fixed manual review sample across the three cases, including an ordinary
relationship, a direct definition, and a dense/qualified neighborhood. For each, record
whether the display is faithful, evidence is verifiable, navigation helps discovery,
and missing relationships reflect data, eligibility, or truncation.

Deliver findings and prioritized defects grouped by extraction, resolution, projection,
and navigation. Decide the next increment from these findings, rather than assuming
the whole corpus or agent should immediately adopt the explorer's operations.

## Verification

Write focused tests for material invariants rather than mirroring the implementation:

- Exact evidence joins and highlighting, including non-BMP Unicode.
- Polarity, attribution, mode, and qualified wording survive projection and rendering.
- Related entities remain distinct; `is` does not merge them or generate inferred edges.
- Parallel edges, missing objects, unresolved/ineligible endpoints, and self-loops.
- Deterministic export and complete coverage accounting.
- Incoming/outgoing filtering and displayed/available counts before and after expansion.
- Search ambiguity, evidence selection from the list, navigation history/reset, and
  artifact failures. Test view behavior independently of canvas pixel coordinates.
- Sidebar renders on both chat and `/graph`; the `Course graph` link is active only on
  `/graph`; the graph route mounts without a populated conversation list. Extend the
  existing `Sidebar` test's `MemoryRouter` pattern rather than adding a new harness.

Run the targeted Python and frontend tests, the required root `.venv/bin/pyright`, and
the frontend build. Run relevant existing citation and routing tests if those components
change. Manually review the real-corpus cases and a narrow viewport; passing automated
checks alone does not demonstrate semantic fidelity or useful exploration.

## Deferred decisions

This increment does not require Neo4j, Sigma.js, new extraction, or a replacement entity
resolver. Defer edge aggregation, whole-corpus visualization, graph editing, and inferred
paths until there is evidence they address a concrete need.

After human exploration is useful, consider sharing neighborhood retrieval with agent
tools. Evaluate separately: tool invocation -> candidate evidence -> selected evidence
-> answer use. Explorer success does not establish an improvement in agent answers.
