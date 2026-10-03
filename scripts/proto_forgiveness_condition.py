"""Reviewable prototype (not wired into the model, prompt, or committed artifact).

Reads the REAL stored claims for one passage (t3-1-5) and renders them two ways, so
we can judge whether distinguishing concept *meaning* -- not just preserving the
condition -- makes the graph read truthfully. Earlier revisions hand-typed the
claims; this reads them from the repository so Render A reflects what is actually
stored, and Render B is *derived from* those claims by the working rule rather than
drawn by hand.

- Render A: the stored claims as-is. One `forgiveness` node; conditional claims are
  dashed and labelled, but the negatives ("empty gesture", "essentially judgemental")
  hang off the same node as "requires correction" -- the ambiguity that makes the
  real graph read wrong.
- Render B: the working rule applied. A conditional claim about forgiveness whose
  evidence carries a condition hinge ("unless"/"without this") and asserts a negative
  property is absorbed as a *description* on a passage-scoped qualified occurrence,
  "forgiveness lacking correction" (descriptions, not separate concept nodes), linked back
  to the base concept by a contextual "qualified use of" edge. "forgiveness entails
  correction" is drawn as an *interpreted requirement* -- reframing the stored conditional
  claim as a requirement is itself an interpretation, so the edge is flagged and its stored
  mode (conditional) kept on the label. The "essentially judgemental rather than healing"
  thought is merged into the judgemental description's text (and its evidence); no
  occurrence->healing edge is drawn. B also adds one *derived* reading: the object-less
  "healing cannot be understood" is reframed as "understanding healing requires right
  perception for healing" (a necessary condition, affirmed), with an "understanding of" link
  back to healing -- all flagged derived; "understanding healing" is the only derived node.
  See _add_understanding_healing. Both renders park object-less claims in a non-projectable
  evidence list rather than drawing a fake "(none)" node.

  A possible "worldly forgiveness" consolidation is deliberately NOT in the claim graph --
  it's a text design note below the graph, since the passage gives no evidence for such a
  grouping and even a dotted node would assert one.

This is an interpretation of ONE passage. "forgiveness lacking correction" is a coined
label, flagged as such; it is not a text-given term (see
docs/qualified-concept-uses-survey.md). Nothing here changes corpus ids, the Claim
model, extraction rules, or apps/web/public/graph/projection.json.

    python scripts/proto_forgiveness_condition.py --out /tmp/proto_forgiveness.html
"""

import argparse
import json
import re
from collections.abc import Callable
from html import escape
from dataclasses import dataclass
from pathlib import Path

from application.retrieval.evidence import source_for_id
from domain.claims.models import Claim, Polarity
from infrastructure.database.claims import list_claims

SOURCE_ID = "t3-1-5"
BASE_CONCEPT = "forgiveness"
BASE_CONCEPT_HEALING = "healing"

# A condition hinge in the evidence span is what licenses treating a claim as a qualified
# occurrence rather than a flat assertion about the base concept.
HINGE = re.compile(r"\b(unless|without|until|if|when|in the absence of)\b", re.I)

# The one claim the condition is *about* keeps hanging off the base concept: forgiveness
# requires correction. Everything else conditional-on-the-same-hinge describes the
# correction-less case, so it reroutes to the qualified occurrence.
BASE_PREDICATES_KEPT = {"requires"}

# Passage-specific: stored claims that extraction labelled flat assertions but whose
# evidence is the predicate of "Without this, it is …" -- so their real scope is the
# without-correction case. Shown with their stored provenance plus that scope, never as
# unconditional. Not a general rule; specific to t3-1-5.
SCOPED_TO_WITHOUT_CORRECTION = {"essentially judgemental"}


@dataclass(frozen=True)
class Rendered:
    title: str
    nodes: list[dict]
    edges: list[dict]
    # Object-less (non-projectable) claims aren't drawn as edges; they're listed with their
    # evidence instead, mirroring how the real graph keeps missing-object claims out of the
    # canvas. One {text, evidence} dict each.
    non_projectable: list[dict]


def _node(node_id: str, label: str, kind: str) -> dict:
    return {"id": node_id, "label": label, "kind": kind}


def _edge(source: str, target: str, label: str, **flags: bool) -> dict:
    return {"source": source, "target": target, "label": label, **flags}


def _non_projectable_entry(c: Claim) -> dict:
    src = source_for_id(c.source_id)
    neg = " · negated" if c.polarity is Polarity.NEGATED else ""
    cond = " · conditional" if c.mode.value == "conditional" else ""
    span = src.text[c.evidence_start : c.evidence_end] if src else ""
    return {"text": f"{c.subject} · {c.verb_phrase}{neg}{cond}", "evidence": span}


def _render_a(claims: list[Claim]) -> Rendered:
    """Stored claims as-is: every subject/object a node, conditionals dashed. Object-less
    claims are non-projectable -- listed with evidence, never drawn as a (none) node."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    non_projectable: list[dict] = []
    for c in claims:
        if c.object is None:
            non_projectable.append(_non_projectable_entry(c))
            continue
        subj_id = f"n:{c.subject}"
        nodes.setdefault(subj_id, _node(subj_id, c.subject, "concept"))
        obj_id = f"n:{c.object}"
        nodes.setdefault(obj_id, _node(obj_id, c.object, "concept"))
        conditional = c.mode.value == "conditional"
        neg = " · negated" if c.polarity is Polarity.NEGATED else ""
        suffix = "\n(stored: conditional)" if conditional else ""
        edges.append(
            _edge(subj_id, obj_id, f"{c.verb_phrase}{neg}{suffix}", conditional=conditional)
        )
    return Rendered(
        "A — stored claims as-is (one forgiveness node)",
        list(nodes.values()),
        edges,
        non_projectable,
    )


def _render_b(claims: list[Claim]) -> Rendered:
    """Working rule applied: reroute hinge-conditioned negative claims about the base
    concept onto a passage-scoped qualified occurrence."""
    base_id = f"n:{BASE_CONCEPT}"
    occ_id = f"occ:{SOURCE_ID}:forgiveness_lacking_correction"

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    non_projectable: list[dict] = []

    def ensure(node_id: str, label: str, kind: str) -> None:
        nodes.setdefault(node_id, _node(node_id, label, kind))

    # Descriptions absorbed onto the occurrence card instead of drawn as nodes/edges: a
    # description ("an empty gesture", "essentially judgemental rather than healing") is a
    # property of forgiveness-lacking-correction, not an independent concept. Each keeps its
    # exact stored evidence. The graph doesn't reify every extracted object into a node.
    descriptions: list[dict] = []
    # The passage states "essentially judgemental rather than healing" as one thought, but
    # extraction split it into "forgiveness is essentially judgemental" + "essentially
    # judgemental contrasts_with healing". Merge the contrast into the matching description
    # text; no occurrence->healing edge is drawn (the relationship stays in the description).
    desc_by_object: dict[str, dict] = {}
    rerouted = False
    for c in claims:
        if c.object is None:
            non_projectable.append(_non_projectable_entry(c))
            continue
        src = source_for_id(c.source_id)
        span = src.text[c.evidence_start : c.evidence_end] if src else ""
        hinged = bool(HINGE.search(span))
        about_base = c.subject.strip().lower() == BASE_CONCEPT

        # A hinge-conditioned "forgiveness is X" claim (not the requires-correction core)
        # describes the correction-less case: absorb X as a description of the occurrence.
        if (
            about_base
            and hinged
            and c.mode.value == "conditional"
            and c.predicate.value not in BASE_PREDICATES_KEPT
        ):
            rerouted = True
            entry = {"text": c.object, "evidence": span}
            descriptions.append(entry)
            desc_by_object[c.object] = entry
            continue

        # "<description> contrasts_with healing": merge "rather than <obj>" into the
        # description text so it reads as the passage does. No edge is drawn to <obj> -- for
        # this prototype the "rather than healing" relationship stays within the description
        # and its evidence, rather than reified as an occurrence->healing edge.
        if c.subject in SCOPED_TO_WITHOUT_CORRECTION and c.predicate.value == "contrasts_with":
            target = desc_by_object.get(c.subject)
            if target is not None:
                target["text"] += f" rather than {c.object}"
                target["evidence"] = span  # the fuller "…rather than healing" span
            continue

        # Everything else is drawn as a normal stored edge (its own concepts).
        subj_id = f"n:{c.subject}"
        obj_id = f"n:{c.object}"
        ensure(subj_id, c.subject, "concept")
        ensure(obj_id, c.object, "concept")
        neg = " · negated" if c.polarity is Polarity.NEGATED else ""
        # "forgiveness entails correction": the passage reads this as a requirement
        # ("unless it entails correction" states what forgiveness MUST do). Reframing the
        # stored conditional claim as an unconditional requirement is itself an
        # interpretation, so the edge is flagged interpreted; the stored mode is kept in the
        # edge's details, not just hinted at.
        is_requirement = about_base and c.predicate.value == "requires"
        if is_requirement:
            # Label carries both the interpretation and the stored fact, since there is no
            # edge-click inspector -- so the reframing is never hidden.
            edges.append(
                _edge(
                    subj_id,
                    obj_id,
                    f"{c.verb_phrase}{neg}\n[interpreted: requirement;\nstored mode: conditional]",
                    interpretation=True,
                )
            )
        else:
            conditional = c.mode.value == "conditional"
            suffix = "\n(stored: conditional)" if conditional else ""
            edges.append(
                _edge(subj_id, obj_id, f"{c.verb_phrase}{neg}{suffix}", conditional=conditional)
            )

    if rerouted:
        ensure(
            occ_id, "forgiveness lacking correction\n[qualified use · t3-1-5]", "occurrence"
        )
        # Descriptions shown beneath the name on the card; details carry each one's exact
        # evidence and the (hard-coded, passage-specific) without-correction scope.
        nodes[occ_id]["label"] += "\n" + "\n".join(
            f"— {d['text']}" for d in descriptions
        )
        nodes[occ_id].update(
            source_id=SOURCE_ID,
            scope="when correction is absent",
            interpretation="Coined label; passage-specific interpretation. Scope hard-coded "
            "(not derived): ‘Without this’ read as ‘without correction’. Descriptions are "
            "stored claims absorbed onto the occurrence, not independent concepts.",
            descriptions=descriptions,
        )
        ensure(base_id, BASE_CONCEPT, "concept")
        edges.append(_edge(occ_id, base_id, "qualified use of", interpretation=True))
        # The "rather than healing" relationship stays within the description text + its
        # evidence (see the contrasts_with branch); no occurrence->healing edge is drawn.
        # NB: a "worldly forgiveness" grouping is deliberately NOT drawn here -- even a
        # dotted node + "may group under" arrow would assert a consolidation this passage
        # gives no evidence for. It's surfaced as a text design note below the graph instead.

    _add_understanding_healing(claims, ensure, edges)

    return Rendered(
        "B — working rule: passage-scoped qualified occurrence",
        list(nodes.values()),
        edges,
        non_projectable,
    )


def _add_understanding_healing(
    claims: list[Claim],
    ensure: Callable[[str, str, str], None],
    edges: list[dict],
) -> None:
    """Derived (passage-scoped) reading of "Until this has occurred healing cannot be
    understood": the object-less negated claim is reframed as a *necessary condition* --
    understanding healing REQUIRES the right perception the miracle induces. The derived
    node, its requires-edge, and its "understanding of" link back to healing are all flagged
    as interpretation. Specific to t3-1-5; no general node-derivation rule here (that waits
    for the durable design).

    Two interpretive moves are made explicit:
      - "until X, Y cannot occur" is reframed as "Y requires X" -- a necessary condition,
        NOT a claim that X guarantees Y.
      - "this" is resolved to the preceding right-perception event (first sentence).
    The requires-edge is affirmed, not negated: the requirement holds positively even though
    the stored claim's polarity is negated.
    """
    src = source_for_id(SOURCE_ID)
    if src is None:
        return
    # Only derive when the passage actually contains the object-less understanding claim and
    # the right-perception target it depends on, so this stays grounded in t3-1-5's claims.
    has_understanding = any(
        c.subject.strip().lower() == "healing"
        and c.object is None
        and "understood" in c.verb_phrase
        for c in claims
    )
    perception_id = "n:right perception for healing"
    has_perception = any(c.object == "right perception for healing" for c in claims)
    if not (has_understanding and has_perception):
        return

    uh_id = f"deriv:{SOURCE_ID}:understanding_healing"
    ensure(uh_id, "understanding healing\n[derived · t3-1-5]", "derived")
    ensure(perception_id, "right perception for healing", "concept")
    ensure(f"n:{BASE_CONCEPT_HEALING}", BASE_CONCEPT_HEALING, "concept")

    edges.append(_edge(uh_id, perception_id, "requires", interpretation=True))
    edges.append(
        _edge(uh_id, f"n:{BASE_CONCEPT_HEALING}", "understanding of", interpretation=True)
    )


HTML = r"""<!doctype html>
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
  .nonproj {{ padding: 0.5rem 1rem; font-size: 0.78rem; color: #6b6880; border-top: 1px dashed #d6d2e8; }}
  .nonproj h3 {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; margin: 0 0 0.3rem; }}
  .nonproj li {{ margin-bottom: 0.3rem; }}
  .nonproj .ev {{ color: #8d88a8; font-style: italic; }}
  #details {{ padding: 1rem 1.25rem; white-space: pre-wrap; border-top: 1px solid #d6d2e8; }}
  .note {{ padding: 0.75rem 1.25rem; font-size: 0.8rem; color: #6b6880; font-style: italic;
          background: #f2f0fa; border-top: 1px dashed #d6d2e8; }}
</style>
</head>
<body>
<header>
  <strong>Prototype — passage {source_id}</strong>  (claims read live from the repository)
  <div class="passage">{passage}</div>
  <div class="flag">Prototype interpretation only — "forgiveness lacking correction" is a
  coined label, not an extracted entity or Course-defined term. Lavender nodes are
  <b>stored surface forms</b> (what extraction emitted), not resolved concepts. Not wired
  into the model/prompt/artifact.</div>
</header>
<div class="grid">
  <div class="pane"><h2 id="ta"></h2><div class="cy" id="cyA"></div>
    <div class="legend">The stored claims verbatim. Conditionals are dashed, but the
    negatives attach to the same <code>forgiveness</code> node as
    <code>requires correction</code> — the ambiguity that reads wrong.</div>
    <div class="nonproj" id="npA"></div></div>
  <div class="pane"><h2 id="tb"></h2><div class="cy" id="cyB"></div>
    <div class="legend"><b>forgiveness lacking correction</b> (orange, dashed) is a
    passage-scoped qualified occurrence; its descriptions ("empty gesture", "essentially
    judgemental rather than healing") sit on the card as text, not as separate nodes — the
    graph doesn't reify every object, and "rather than healing" stays within the
    description. The dashed <b>qualified use of</b> edge links it to
    <code>forgiveness</code> — contextual, never identity/doctrine. <b>understanding
    healing</b> (green, dashed) is the only derived node here: "healing cannot be understood"
    reframed as understanding <b>requires</b> right perception (a necessary condition, not a
    guarantee), linked by <b>understanding of</b> back to healing. <code>forgiveness entails
    correction</code> is drawn as an <b>interpreted requirement</b> (dashed), with its stored
    mode (conditional) kept on the label. Click the orange card for each description's exact
    evidence.</div>
    <div class="nonproj" id="npB"></div></div>
</div>
<div id="details">Select the orange qualified occurrence to inspect its descriptions, scope, and evidence.</div>
<div class="note">Deferred design note (NOT drawn in the graph): several passage-scoped
qualified occurrences of a concept <em>might</em> later consolidate under a shared illusory
concept (e.g. "worldly forgiveness") — but only on evidence that they share a meaning, which
this passage does not provide. Kept out of the claim graph deliberately: even a dotted node
would assert a grouping the text here doesn't support. See
docs/qualified-concept-uses-survey.md.</div>
<script>
const A = {graph_a};
const B = {graph_b};

const style = [
  {{ selector: "node", style: {{
      "label": "data(label)", "font-size": "11px", "text-wrap": "wrap",
      "text-max-width": "130px", "background-color": "#eceaf6", "border-width": 1,
      "border-color": "#d6d2e8", "color": "#2a2740", "text-valign": "center",
      "text-halign": "center", "width": "label", "height": "label", "padding": "10px",
      "shape": "round-rectangle" }} }},
  {{ selector: 'node[kind = "occurrence"]', style: {{
      "background-color": "#fbe8d2", "border-color": "#d98a2b", "border-width": 2,
      "border-style": "dashed", "color": "#6b3b00", "text-max-width": "200px",
      "font-size": "10px", "text-wrap": "wrap" }} }},
  {{ selector: 'node[kind = "derived"]', style: {{
      "background-color": "#def0e4", "border-color": "#2b8a52", "border-width": 2,
      "border-style": "dashed", "color": "#13522f" }} }},
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
];

function render(elId, g) {{
  const els = [
    ...g.nodes.map(n => ({{ data: n }})),
    ...g.edges.map((e, i) => ({{ data: {{
        id: "e" + i, source: e.source, target: e.target, label: e.label,
        conditional: e.conditional ? "true" : "false",
        interpretation: e.interpretation ? "true" : "false" }} }})),
  ];
  const cy = cytoscape({{ container: document.getElementById(elId), elements: els,
    style, minZoom: 0.2, maxZoom: 2.5 }});
  cy.layout({{ name: "breadthfirst", directed: true, padding: 30, spacingFactor: 1.3 }}).run();
  cy.fit(undefined, 40);
  cy.on("tap", "node[kind = 'occurrence']", event => {{
    const n = event.target.data();
    const descs = (n.descriptions || [])
      .map(d => "  • " + d.text + "\n    “" + d.evidence + "”")
      .join("\n");
    document.getElementById("details").textContent =
      "forgiveness lacking correction\n\nScope: " + n.scope + "\n" + n.interpretation +
      "\n\nDescribed as (stored claims, absorbed):\n" + descs;
  }});
}}

function renderNonProjectable(elId, g) {{
  const el = document.getElementById(elId);
  if (!g.non_projectable || g.non_projectable.length === 0) {{ el.textContent = ""; return; }}
  const items = g.non_projectable.map(
    e => "<li>" + e.text + "<br><span class='ev'>“" + e.evidence + "”</span></li>"
  ).join("");
  el.innerHTML = "<h3>Non-projectable — object-less, not drawn</h3><ul>" + items + "</ul>";
}}

document.getElementById("ta").textContent = A.title;
document.getElementById("tb").textContent = B.title;
renderNonProjectable("npA", A);
renderNonProjectable("npB", B);
render("cyA", A);
render("cyB", B);
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prototype: qualified-occurrence rendering.")
    parser.add_argument("--out", type=Path, default=Path("/tmp/proto_forgiveness.html"))
    args = parser.parse_args(argv)

    source = source_for_id(SOURCE_ID)
    if source is None:
        raise SystemExit(f"source {SOURCE_ID} not found")
    claims = sorted(
        (c for c in list_claims() if c.source_id == SOURCE_ID),
        key=lambda c: (c.evidence_start, c.evidence_end),
    )
    if not claims:
        raise SystemExit(f"no stored claims for {SOURCE_ID}")

    a = _render_a(claims)
    b = _render_b(claims)

    def blob(r: Rendered) -> str:
        return json.dumps(
            {
                "title": r.title,
                "nodes": r.nodes,
                "edges": r.edges,
                "non_projectable": r.non_projectable,
            }
        )

    html = HTML.format(
        source_id=SOURCE_ID,
        passage=escape(source.text),
        graph_a=blob(a),
        graph_b=blob(b),
    )
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out}  ({len(claims)} stored claims for {SOURCE_ID})")
    print("Open it in a browser to compare render A (stored) vs B (working rule).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
