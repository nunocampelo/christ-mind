import type {
  GraphArtifact,
  GraphEdge,
  GraphNode,
  NonProjectable,
  PassageRef,
} from "@/api/graphArtifact";
import { SCHEMA_VERSION } from "@/api/graphArtifact";

// A hand-built artifact exercising the invariants the view model must preserve: a merged
// node (two expressions) and singletons, parallel edges between the same pair, a self-loop,
// a negated edge, an `is` definition that must NOT merge its endpoints, a non-BMP clause,
// and a non-projectable (missing-object) claim. Kept small so the asserted shapes are
// obvious; semantics mirror the Python projection (plan 0030).

const node = (
  node_id: string,
  label: string,
  expressions: string[],
  entity_id: string | null = null,
): GraphNode => ({ node_id, label, entity_id, expressions });

export const F = node("e:f1", "forgiveness", ["Forgiveness", "forgiveness"], "f1");
export const H = node("m:healing", "healing", ["healing"]);
export const G = node("m:God", "God", ["God"]);
export const RM = node("m:right-mindedness", "right-mindedness", ["right-mindedness"]);
// A concept that participates ONLY in a non-projectable claim: it has a node (so it is
// searchable) but no drawable edge. Mirrors the Python exporter registering endpoints
// independent of drawability.
export const AT = node("m:atonement", "atonement", ["atonement"]);

const edge = (over: Partial<GraphEdge> & Pick<GraphEdge, "claim_id">): GraphEdge => ({
  source_node_id: F.node_id,
  target_node_id: H.node_id,
  subject: "forgiveness",
  object: "healing",
  predicate: "causes",
  verb_phrase: "brings about",
  polarity: "affirmed",
  mode: "assertion",
  attribution: "course",
  source_id: "s1",
  evidence_start: 0,
  evidence_end: 10,
  ...over,
});

// Two parallel edges forgiveness→healing (distinct claims, same pair, must stay distinct),
// one negated so polarity survival is observable. The negated clause carries a non-BMP char
// in its surrounding text to exercise offset-safe segment rendering.
export const E_CAUSES = edge({ claim_id: "c_causes" });
export const E_CAUSES_NEG = edge({
  claim_id: "c_causes_neg",
  predicate: "undoes",
  object: "healing",
  verb_phrase: "undoes fear in",
  polarity: "negated",
  source_id: "s2",
  evidence_start: 5,
  evidence_end: 20,
});
// An incoming edge God→forgiveness, so direction filtering is observable.
export const E_INCOMING = edge({
  claim_id: "c_incoming",
  source_node_id: G.node_id,
  target_node_id: F.node_id,
  subject: "God",
  object: "forgiveness",
  predicate: "expresses",
  verb_phrase: "expresses",
  source_id: "s3",
  evidence_start: 0,
  evidence_end: 8,
});
// A self-loop on forgiveness (appears in both out and in lists → must dedupe to one).
export const E_SELF = edge({
  claim_id: "c_self",
  target_node_id: F.node_id,
  object: "forgiveness",
  predicate: "requires",
  verb_phrase: "requires",
  source_id: "s4",
  evidence_start: 1,
  evidence_end: 9,
});
// `is` definition God is right-mindedness — must NOT merge the two nodes.
export const E_IS = edge({
  claim_id: "c_is",
  source_node_id: G.node_id,
  target_node_id: RM.node_id,
  subject: "God",
  object: "right-mindedness",
  predicate: "is",
  verb_phrase: "is",
  source_id: "s5",
  evidence_start: 0,
  evidence_end: 6,
});

// Non-projectable: forgiveness makes <missing object>. Participates via its subject.
export const NP: NonProjectable = {
  claim_id: "np1",
  subject: "forgiveness",
  object: null,
  predicate: "makes",
  verb_phrase: "makes",
  polarity: "affirmed",
  mode: "assertion",
  attribution: "course",
  reason: "missing_object",
  source_id: "s6",
  evidence_start: 2,
  evidence_end: 11,
};

// Non-projectable claim whose subject (atonement) appears in no drawable edge — the only
// way to reach it is via its node. Conditional + ego-attributed so qualifier rendering is
// observable on a non-projectable claim too.
export const NP_ATONEMENT: NonProjectable = {
  claim_id: "np2",
  subject: "atonement",
  object: null,
  predicate: "makes",
  verb_phrase: "would make",
  polarity: "affirmed",
  mode: "conditional",
  attribution: "ego",
  reason: "missing_object",
  source_id: "s7",
  evidence_start: 0,
  evidence_end: 9,
};

// Passages carry pre-sliced segments; the non-BMP astral char lives in a clause whose span
// the frontend must never re-slice on code-unit offsets.
const passage = (over: Partial<PassageRef> & Pick<PassageRef, "source_id" | "evidence">): PassageRef => ({
  book: "ACIM",
  chapter: 1,
  verse: null,
  section: 1,
  paragraph: 1,
  edition: "Sparkly Edition",
  ...over,
});

export const PASSAGES: PassageRef[] = [
  passage({
    source_id: "s1",
    evidence: {
      before: "Truly, ",
      clause: "forgiveness brings about healing",
      after: ".",
      evidence_start: 0,
      evidence_end: 10,
    },
  }),
  passage({
    source_id: "s2",
    evidence: {
      // non-BMP astral char in the surrounding text — segment is pre-sliced in Python.
      before: "👁 ",
      clause: "forgiveness undoes fear",
      after: " entirely.",
      evidence_start: 5,
      evidence_end: 20,
    },
  }),
  passage({
    source_id: "s3",
    evidence: { before: "", clause: "God expresses forgiveness", after: "", evidence_start: 0, evidence_end: 8 },
  }),
  passage({
    source_id: "s6",
    evidence: { before: "", clause: "forgiveness makes", after: " all things new", evidence_start: 2, evidence_end: 11 },
  }),
  passage({
    source_id: "s7",
    evidence: { before: "", clause: "atonement", after: " would be undone", evidence_start: 0, evidence_end: 9 },
  }),
];

export const makeArtifact = (): GraphArtifact => ({
  metadata: {
    schema_version: SCHEMA_VERSION,
    content_hash: "test-hash",
    claim_count: 7,
    resolution_entity_count: 1,
    source_count: 7,
  },
  nodes: [F, H, G, RM, AT],
  edges: [E_CAUSES, E_CAUSES_NEG, E_INCOMING, E_SELF, E_IS],
  non_projectable: [NP, NP_ATONEMENT],
  passages: PASSAGES,
});
