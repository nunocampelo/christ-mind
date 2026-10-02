# Markdown citation pipeline: recognize once in mdast, inject in the AST

Implements plan **0028 item 7-md**.

## Context

In `apps/web/src/components/chat/CitedAnswer.tsx`, `CitedProse` renders full Markdown
(`MarkdownMessage`) **only** when an answer has no citations; once a marker resolves it falls
back to `parseCitedProse` string-splitting and renders each text run as a plain `<span>`
(`CitedAnswer.tsx:143`). So any cited answer renders Markdown **literally** (`**bold**`, `-
lists`, headings show as raw syntax), and splitting the string first would break any construct
spanning a marker.

Fix (0028's explicit choice): **parse the whole answer once, then inject citation markers into
the syntax tree** so Markdown is parsed on the complete answer and citations land at their exact
positions — including mid-list or inside `**bold**`.

**Key design decision (from review):** recognition must be **Markdown-aware** and happen in **one
pass over mdast** — not a raw-string regex, and not a hast walker that re-recognizes markers
independently. A raw regex (today's `parseCitedProse`) and a post-Markdown tree disagree once
Markdown reinterprets the source, so sharing only an ordinal map cannot guarantee that the
numbers the Sources panel shows match the superscripts actually injected. The single mdast pass
produces **both** the transformed tree **and** the ordinal map, so recognition, numbering, and
placement are the same decision.

### Verified against the installed pipeline (react-markdown 10.1.0, remark-gfm 4.0.1)

Running the real remark pipeline confirmed each edge case and the injection mechanism:

| Source | mdast | Policy |
|---|---|---|
| `**bold [c1]**` | `[c1]` in a `text` node under `strong` | recognize → citation |
| `stmt [c1].` | `[c1]` in a `text` node under `paragraph` | recognize → citation |
| `\[c1\]` (escaped) | `text.value === "[c1]"` but node `position` points at source `\[c1\]` | **skip** via source-offset check; no ordinal |
| `` `foo[c1]` `` / fenced | `inlineCode` / `code` node (not `text`) | **skip** (verbatim); no ordinal |
| `[c1]` + `[c1]: url` (ref def) | becomes a `linkReference`; the `text` value is `"c1"` (no brackets) | naturally unrecognized; no ordinal |
| `[t [c1]](url)` (link label) | `[c1]` in a `text` node under `link` | recognize → **plain `<sup>`** (consume ordinal, never `<a>`-in-`<a>`) |

- A custom mdast node with `data = { hName: "cited-marker", hProperties: { claimId, ordinal,
  resolved } }` survives `remark-rehype` into a hast `<cited-marker>` element — confirmed. So the
  node is injected in **mdast** and rendered via react-markdown's `components` override, with
  values read off the `node` prop (`passNode: true`).
- `unist-util-visit`, `@types/mdast`, `@types/hast` are already present transitively via
  react-markdown — **no new dependency**.

## Approach

One render path: `CitedProse` always runs `ReactMarkdown` with `remarkGfm` + one custom remark
plugin that recognizes markers over mdast, assigns ordinals in document order under the policies
above, and injects `cited-marker` nodes. The plugin is a no-op when there are no markers, so the
uncited case needs no separate branch.

### 1. Single recognition pass — new `src/components/chat/citedMarkerMdast.ts`

A function usable **both** as a remark plugin **and** standalone (for the ordinal map / clipboard):

- `recognizeCitations(tree, { ordinals, pending })` walks mdast with `unist-util-visit` carrying
  node ancestry/context:
  - **Skip** `inlineCode`, `code`, `definition` nodes entirely (verbatim / not prose).
  - For `text` nodes, match the marker regex `/\[([A-Za-z0-9][A-Za-z0-9._-]*)\]/g` **and**
    confirm against the node's `position` source slice that the brackets are literal (not an
    escaped `\[…\]`); an escaped span is left as text, no ordinal.
  - Track whether the current text node is inside a `link` ancestor → emit a **non-link** marker
    (plain `<sup>`, `resolved:false`-style rendering) even when the claim resolves, to avoid
    `<a>`-in-`<a>`. Still consumes an ordinal.
  - Ordinal assignment: by first appearance in document order, over the markers that pass the
    policy above (so skipped code/escaped/ref-def markers never shift the numbering).
  - Final mode: an id with no matching claim is **stripped** (no node, no literal `[id]`).
    Pending (streaming) mode: every eligible well-formed id becomes a pending marker node
    (`resolved:false`), numbered by appearance.
  - Replace each recognized marker's text with `[text?, citationNode, text?]`, where
    `citationNode.data = { hName: CITED_MARKER_TAG, hProperties: { claimId, ordinal, resolved } }`.
- Export `citationOrdinals(markdown, claims, pending=false): Map<string, {ordinal, claim}>` that
  parses the markdown to mdast (reuse the same `unified().use(remarkParse).use(remarkGfm)`) and
  runs the recognition pass purely to collect the map — the **single source** consumed by the
  Sources panel (and clipboard). It cannot diverge from injection because it is the same pass.
- Export `rehypeless` remark plugin wrapper `remarkCitedMarkers(options)` returning
  `(tree) => recognizeCitations(tree, options)` for use in `remarkPlugins`.

### 2. Marker renderer — new `src/components/chat/CitationMarker.tsx`

`makeCitationMarker({ turnId, jumpToSource, sourceAnchor })` returns a component reading
`claimId`/`ordinal`/`resolved` off the `node.properties`:
- `resolved === false` (pending, or inside a link) → `<sup className="cited-marker
  cited-marker-pending" aria-hidden>{ordinal}</sup>`.
- else → `<a className="cited-marker" href="#anchor" aria-label={`Source ${ordinal}`}
  onClick={preventDefault → jumpToSource}>{ordinal}</a>`.
Identical markup to today's segments, so existing assertions hold.

### 3. Rewrite `CitedProse` — `src/components/chat/CitedAnswer.tsx`

```tsx
const components = {
  [CITED_MARKER_TAG]: makeCitationMarker({ turnId, jumpToSource, sourceAnchor }),
} as Components; // runtime resolves the custom tagName; only the static type is narrow
return (
  <div className="agent-markdown cited-prose">
    <ReactMarkdown
      remarkPlugins={[remarkGfm, [remarkCitedMarkers, { claims, pending }]]}
      components={components}
    >
      {text}
    </ReactMarkdown>
  </div>
);
```
- Remove the unused `MarkdownMessage` import (keep `MarkdownMessage.tsx` — still used by
  `Transcript.tsx` for user turns).
- Replace the Sources-panel ordinal loop (`CitedAnswer.tsx:180-185`) with `citationOrdinals(...)`;
  `sortedClaims` unchanged.
- Keep `sourceAnchor`/`jumpToSource` in `CitedAnswer.tsx`, passed into the factory.

### 4. `parseCitedProse` / clipboard parity — `src/api/agentApi.ts` + `copyAnswer.ts`

`copyAnswer.ts` renders `[1]`-style ordinals for the clipboard via `parseCitedProse`. To keep
clipboard numbering in agreement with the rendered superscripts, re-express the clipboard
ordinals on the **same** mdast recognition (`citationOrdinals`) rather than the raw regex. Options
to decide in implementation: (a) keep `parseCitedProse` for its segment API but make clipboard
numbering come from `citationOrdinals`, or (b) retire the raw-regex numbering entirely. Either
way the authority is the mdast pass.

### 5. CSS — `src/components/chat/chat.css`

Drop `white-space: pre-wrap` from `.cited-prose` (the cited path now renders real Markdown blocks;
`pre-wrap` would inject blank lines between `<p>`/`<li>`). Keep the class on the div; update the
comment.

## Files

| File | Change |
|---|---|
| `src/components/chat/citedMarkerMdast.ts` | **new** — `CITED_MARKER_TAG`, `recognizeCitations`, `remarkCitedMarkers`, `citationOrdinals` |
| `src/components/chat/CitationMarker.tsx` | **new** — `makeCitationMarker` |
| `src/components/chat/CitedAnswer.tsx` | one ReactMarkdown pipeline; shared ordinals; drop `MarkdownMessage` import |
| `src/components/chat/chat.css` | remove `white-space: pre-wrap` from `.cited-prose`; update comment |
| `src/api/agentApi.ts` / `src/api/copyAnswer.ts` | clipboard numbering sourced from `citationOrdinals` |
| `src/components/chat/CitedAnswer.test.tsx` | new tests (below) |
| `src/api/agentApi.test.ts` | adjust if `parseCitedProse` behavior/segments change |

## Tests (`CitedAnswer.test.tsx`, plus mdast-pass unit tests)

Beyond the happy path:
- **Citation inside bold:** `**statement [c1]**` → real `<strong>` containing an inline `Source 1`
  link; no literal `[c1]`/`**`.
- **Citation mid-list:** marker inside one `<li>` of a `-` list → two `<li>`, inline link in the
  first, list not broken.
- **Repeated + unknown markers:** repeated `[c1]` reuse ordinal 1; an unknown id is stripped in
  final mode (no literal brackets); an answer of **only** unknown markers renders clean prose with
  no superscripts.
- **Edge policies:** link label (`[t [c1]](url)` → plain `<sup>`, never `<a>`-in-`<a>`); inline
  code and fenced code (`[c1]` stays literal, consumes no ordinal, so a following real marker is
  still `1`); escaped `\[c1\]` stays literal, no ordinal; ref-def `[c1]`/`[c1]: url` keeps link
  semantics, no citation ordinal.
- **Streaming → resolved rerender:** pending markers render as bare numbered `<sup>` (no link);
  after the evidence artifact lands, a rerender turns the same markers into working `Source N`
  links.
- **Ordinal agreement:** the Sources panel ordinals equal the injected superscript numbers across
  the code/escaped/ref-def cases (the thing the single pass guarantees).

## Risks

- **Highest:** the custom `cited-marker` tagName must render — verified at runtime (hast
  `data.hName` → element; react-markdown resolves tagName via `components`; `passNode` supplies
  `node.properties`). The "inline superscript, not literal marker" test guards it.
- Divergence between panel and prose numbering is structurally prevented by the single pass; the
  edge-case tests above lock the policies.

## Verification

- `cd apps/web && npm run test` — full suite incl. the new mdast/citation tests.
- `cd apps/web && npm run build` — production build (runs `tsc -b`, so typecheck is covered here;
  no separate typecheck step). The only expected TS workaround is the `as Components` cast for the
  custom tag key.
- Manual (optional): ask a question whose answer has a list/bold with a citation; confirm real
  Markdown with inline superscripts and no literal `[c1]`.
