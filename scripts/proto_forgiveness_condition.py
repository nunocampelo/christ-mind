"""THROWAWAY prototype (not wired into the model, prompt, or committed artifact).

Hand-builds the forgiveness/correction passage (t3-1-5) two ways and emits a
self-contained HTML page that renders both graphs with Cytoscape (CDN), so we can
judge whether distinguishing concept *meaning* -- not just preserving the
condition -- makes the graph read truthfully.

It answers a question the real pipeline can't yet: a `condition` field would keep
"empty/judgemental hold when correction is absent", but both the positive and the
negative claims would still hang off ONE undifferentiated `forgiveness` node.

Render B introduces "forgiveness lacking correction" NOT as a permanent new concept
sense but as a *condition-qualified occurrence of forgiveness scoped to this
passage*, carrying the full passage as evidence and linked back to the base concept
`forgiveness` by a contextual "qualified use of" edge -- never identity or doctrine.
It also sketches the DEFERRED next tier: several such passage-scoped occurrences may
eventually group under a shared illusory concept ("worldly forgiveness"), but only
when textual evidence shows they MEAN the same thing -- not merely that each is
negative/illusory. That grouping is drawn as a not-yet placeholder, never asserted.

Honesty note carried into the render: `forgiveness --requires--> correction` is
itself a proposed reading of this passage; the STORED claim marks it `conditional`.
The prototype labels it as such rather than as a settled fact.

Nothing here changes corpus ids, the Claim model, extraction rules, or
apps/web/public/graph/projection.json. Kept as a reviewable example (not deleted).

    python scripts/proto_forgiveness_condition.py --out /tmp/proto_forgiveness.html
"""

import argparse
import json
from pathlib import Path

SOURCE_ID = "t3-1-5"
PASSAGE = (
    "5. The level-adjustment power of the miracle induces the right perception for "
    "healing. Until this has occurred healing cannot be understood. Forgiveness is an "
    "empty gesture unless it entails correction. Without this, it is essentially "
    "judgemental rather than healing."
)

# Render A: one forgiveness node; the condition rides the negative edges.
# Tests whether a condition field ALONE is enough. The `requires correction` edge is
# marked conditional too, matching the STORED claim (t3-1-5), not drawn as settled.
GRAPH_A = {
    "title": "A — one node, condition on the edge",
    "nodes": [
        {"id": "forgiveness", "label": "forgiveness", "kind": "concept"},
        {"id": "correction", "label": "correction", "kind": "concept"},
        {"id": "empty", "label": "empty gesture", "kind": "concept"},
        {"id": "judge", "label": "essentially judgemental", "kind": "concept"},
    ],
    "edges": [
        {
            "source": "forgiveness",
            "target": "correction",
            "label": "requires\n(stored: conditional)",
            "conditional": True,
        },
        {
            "source": "forgiveness",
            "target": "empty",
            "label": "is\n(when correction absent)",
            "conditional": True,
        },
        {
            "source": "forgiveness",
            "target": "judge",
            "label": "is\n(when correction absent)",
            "conditional": True,
        },
    ],
}

# Render B: three tiers.
#  1. "forgiveness lacking correction" — a condition-qualified occurrence scoped to THIS
#     passage (not a permanent concept sense), carrying the negative branch.
#  2. a dashed contextual "qualified use of" edge back to the base concept forgiveness.
#  3. a DEFERRED grouping placeholder: passage-scoped occurrences MAY later group under a
#     shared illusory concept ("worldly forgiveness") when evidence shows they mean the
#     same thing. Drawn as not-yet, never asserted.
# The `requires correction` edge is labelled as the stored-conditional reading it is.
GRAPH_B = {
    "title": "B — passage-scoped qualified occurrence (+ deferred grouping)",
    "nodes": [
        {"id": "forgiveness", "label": "forgiveness", "kind": "concept"},
        {"id": "correction", "label": "correction", "kind": "concept"},
        {"id": "empty", "label": "empty gesture", "kind": "concept"},
        {"id": "judge", "label": "essentially judgemental", "kind": "concept"},
        {
            "id": "forgiveness_lacking",
            "label": "forgiveness lacking correction\n[qualified use · t3-1-5]",
            "kind": "occurrence",
        },
        {
            "id": "worldly",
            "label": "worldly forgiveness\n[deferred — needs evidence]",
            "kind": "deferred",
        },
    ],
    "edges": [
        {
            "source": "forgiveness",
            "target": "correction",
            "label": "requires\n(stored: conditional)",
            "conditional": True,
        },
        {"source": "forgiveness_lacking", "target": "empty", "label": "is"},
        {"source": "forgiveness_lacking", "target": "judge", "label": "is"},
        {
            "source": "forgiveness_lacking",
            "target": "forgiveness",
            "label": "qualified use of",
            "interpretation": True,
        },
        {
            "source": "forgiveness_lacking",
            "target": "worldly",
            "label": "may group under\n(when evidence supports)",
            "deferred": True,
        },
    ],
}

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Prototype — forgiveness / correction (t3-1-5)</title>
<script src="https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js"></script>
<style>
  :root {{ color-scheme: light; }}
  body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; background: #faf9f5; color: #2a2740; }}
  header {{ padding: 1rem 1.25rem; border-bottom: 1px solid #d6d2e8; }}
  header .passage {{ color: #4a4660; max-width: 60rem; margin-top: 0.5rem; }}
  header .flag {{ color: #8a2b2b; font-style: italic; margin-top: 0.5rem; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: #d6d2e8; }}
  .pane {{ background: #faf9f5; display: flex; flex-direction: column; min-height: 70vh; }}
  .pane h2 {{ font-size: 0.95rem; margin: 0; padding: 0.6rem 1rem; border-bottom: 1px solid #e7e4f2; }}
  .cy {{ flex: 1; }}
  .legend {{ padding: 0.5rem 1rem; font-size: 0.8rem; color: #6b6880; border-top: 1px solid #e7e4f2; }}
  .legend b {{ color: #8a2b2b; }}
</style>
</head>
<body>
<header>
  <strong>Prototype — passage {source_id}</strong>
  <div class="passage">{passage}</div>
  <div class="flag">Prototype interpretation only — not an extracted entity, not a
  Course-defined term, not wired into the model/prompt/artifact.</div>
</header>
<div class="grid">
  <div class="pane"><h2 id="ta"></h2><div class="cy" id="cyA"></div>
    <div class="legend">One <code>forgiveness</code> node. The negative claims carry a
    condition on the edge, but still attach to the same node as
    <code>requires correction</code> — and that edge is itself only
    <b>stored-conditional</b>, not a settled fact.</div></div>
  <div class="pane"><h2 id="tb"></h2><div class="cy" id="cyB"></div>
    <div class="legend"><b>forgiveness lacking correction</b> (orange, dashed) is a
    <b>condition-qualified occurrence scoped to this passage</b>, not a permanent concept
    sense; the dashed <b>qualified use of</b> edge links it to <code>forgiveness</code> —
    contextual, never identity/doctrine. The dotted <b>worldly forgiveness</b> node + <b>may
    group under</b> edge are a <b>deferred</b> tier: several passage occurrences could later
    consolidate there, but only on evidence of shared meaning. <code>requires correction</code>
    is labelled as the stored-conditional reading it is.</div></div>
</div>
<script>
const A = {graph_a};
const B = {graph_b};

const style = [
  {{ selector: "node", style: {{
      "label": "data(label)", "font-size": "11px", "text-wrap": "wrap",
      "text-max-width": "120px", "background-color": "#eceaf6", "border-width": 1,
      "border-color": "#d6d2e8", "color": "#2a2740", "text-valign": "center",
      "text-halign": "center", "width": "label", "height": "label", "padding": "10px",
      "shape": "round-rectangle" }} }},
  {{ selector: 'node[kind = "occurrence"]', style: {{
      "background-color": "#fbe8d2", "border-color": "#d98a2b", "border-width": 2,
      "border-style": "dashed", "color": "#6b3b00" }} }},
  {{ selector: 'node[kind = "deferred"]', style: {{
      "background-color": "#f2f0fa", "border-color": "#b9b4d4", "border-width": 1,
      "border-style": "dotted", "color": "#8d88a8", "font-style": "italic" }} }},
  {{ selector: "edge", style: {{
      "label": "data(label)", "font-size": "10px", "text-wrap": "wrap", "color": "#6b6880",
      "curve-style": "bezier", "target-arrow-shape": "triangle", "arrow-scale": 0.9,
      "line-color": "#b9b4d4", "target-arrow-color": "#b9b4d4", "width": 1.5,
      "text-rotation": "autorotate", "text-background-color": "#faf9f5",
      "text-background-opacity": 0.9, "text-background-padding": "3px" }} }},
  {{ selector: 'edge[conditional = "true"]', style: {{
      "line-style": "dashed", "color": "#8a2b2b" }} }},
  {{ selector: 'edge[interpretation = "true"]', style: {{
      "line-style": "dashed", "line-color": "#d98a2b", "target-arrow-color": "#d98a2b",
      "color": "#6b3b00", "line-dash-pattern": [4, 4] }} }},
  {{ selector: 'edge[deferred = "true"]', style: {{
      "line-style": "dotted", "line-color": "#b9b4d4", "target-arrow-color": "#b9b4d4",
      "color": "#8d88a8", "target-arrow-shape": "triangle-tee" }} }},
];

function render(elId, g) {{
  const els = [
    ...g.nodes.map(n => ({{ data: {{ id: n.id, label: n.label, kind: n.kind }} }})),
    ...g.edges.map((e, i) => ({{ data: {{
        id: "e" + i, source: e.source, target: e.target, label: e.label,
        conditional: e.conditional ? "true" : "false",
        interpretation: e.interpretation ? "true" : "false",
        deferred: e.deferred ? "true" : "false" }} }})),
  ];
  const cy = cytoscape({{ container: document.getElementById(elId), elements: els,
    style, minZoom: 0.2, maxZoom: 2.5 }});
  cy.layout({{ name: "breadthfirst", directed: true, padding: 30, spacingFactor: 1.3 }}).run();
  cy.fit(undefined, 40);
}}

document.getElementById("ta").textContent = A.title;
document.getElementById("tb").textContent = B.title;
render("cyA", A);
render("cyB", B);
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/proto_forgiveness.html"))
    args = parser.parse_args(argv)

    html = HTML.format(
        source_id=SOURCE_ID,
        passage=PASSAGE,
        graph_a=json.dumps(GRAPH_A),
        graph_b=json.dumps(GRAPH_B),
    )
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out}")
    print("Open it in a browser to compare render A (one node) vs B (qualified-subject node).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
