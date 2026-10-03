// Pure neighborhood logic over a loaded artifact — no Cytoscape, no React (plan 0030, C).
// This is the view model the canvas and the relationship list both render, and what the
// tests exercise directly: a neighborhood, its filtered counts, and the claims that
// participate but can't be drawn. Deterministic throughout so the same selection always
// yields the same order.

import {
  type GraphArtifact,
  type GraphEdge,
  type GraphNode,
  type NonProjectable,
  type PassageRef,
  type Predicate,
  passageKey,
} from "@/api/graphArtifact";

export const NEIGHBORHOOD_CAP = 20;

export type Direction = "both" | "incoming" | "outgoing";

export interface GraphFilters {
  direction: Direction;
  predicates: Set<Predicate>; // empty = all predicates
}

export const ALL_DIRECTIONS: Direction = "both";

export const defaultFilters = (): GraphFilters => ({
  direction: "both",
  predicates: new Set(),
});

// An indexed artifact: lookups the view model needs, built once per load.
export interface GraphIndex {
  artifact: GraphArtifact;
  nodeById: Map<string, GraphNode>;
  edgesBySource: Map<string, GraphEdge[]>;
  edgesByTarget: Map<string, GraphEdge[]>;
  passageByKey: Map<string, PassageRef>;
  // non-projectable claims keyed by a participating surface form, so a selected node can
  // surface the undrawable claims it takes part in.
  nonProjectableBySurface: Map<string, NonProjectable[]>;
}

export const buildIndex = (artifact: GraphArtifact): GraphIndex => {
  const nodeById = new Map(artifact.nodes.map((n) => [n.node_id, n]));
  const edgesBySource = new Map<string, GraphEdge[]>();
  const edgesByTarget = new Map<string, GraphEdge[]>();
  for (const e of artifact.edges) {
    (edgesBySource.get(e.source_node_id) ?? setGet(edgesBySource, e.source_node_id)).push(e);
    (edgesByTarget.get(e.target_node_id) ?? setGet(edgesByTarget, e.target_node_id)).push(e);
  }
  const passageByKey = new Map(
    artifact.passages.map((p) => [
      passageKey(p.source_id, p.evidence.evidence_start, p.evidence.evidence_end),
      p,
    ]),
  );
  const nonProjectableBySurface = new Map<string, NonProjectable[]>();
  for (const np of artifact.non_projectable) {
    for (const form of [np.subject, np.object].filter((f): f is string => f !== null)) {
      (nonProjectableBySurface.get(form) ?? setGet(nonProjectableBySurface, form)).push(np);
    }
  }
  return {
    artifact,
    nodeById,
    edgesBySource,
    edgesByTarget,
    passageByKey,
    nonProjectableBySurface,
  };
};

const setGet = <T>(m: Map<string, T[]>, k: string): T[] => {
  const v: T[] = [];
  m.set(k, v);
  return v;
};

const matchesFilters = (edge: GraphEdge, filters: GraphFilters): boolean =>
  filters.predicates.size === 0 || filters.predicates.has(edge.predicate);

// Deterministic edge order: predicate, then the far endpoint's node id, then claim id.
const orderEdges = (edges: GraphEdge[], centerId: string): GraphEdge[] =>
  [...edges].sort((a, b) => {
    if (a.predicate !== b.predicate) return a.predicate < b.predicate ? -1 : 1;
    const fa = a.source_node_id === centerId ? a.target_node_id : a.source_node_id;
    const fb = b.source_node_id === centerId ? b.target_node_id : b.source_node_id;
    if (fa !== fb) return fa < fb ? -1 : 1;
    return a.claim_id < b.claim_id ? -1 : a.claim_id > b.claim_id ? 1 : 0;
  });

export interface Neighborhood {
  center: GraphNode;
  // edges shown after filtering + cap, each with its resolved far endpoint
  edges: GraphEdge[];
  neighbors: GraphNode[];
  nonProjectable: NonProjectable[];
  // every predicate present on this center's eligible edges, before the filter and cap, so
  // the filter row offers the full set rather than only the predicates that survived.
  allPredicates: Predicate[];
  counts: NeighborhoodCounts;
}

export interface NeighborhoodCounts {
  displayed: number; // edges actually drawn (after filter + cap)
  availableAfterFilter: number; // eligible edges matching the filter, before the cap
  totalEligible: number; // all eligible edges on this node, ignoring the filter
  hiddenByCap: number; // availableAfterFilter - displayed
  nonProjectable: number; // participating claims that can't be drawn
}

// Build the one-hop neighborhood of `centerId` under `filters`, capped at `cap`.
export const neighborhood = (
  index: GraphIndex,
  centerId: string,
  filters: GraphFilters,
  cap = NEIGHBORHOOD_CAP,
): Neighborhood | null => {
  const center = index.nodeById.get(centerId);
  if (!center) return null;

  const outgoing = index.edgesBySource.get(centerId) ?? [];
  const incoming = index.edgesByTarget.get(centerId) ?? [];
  const byDirection =
    filters.direction === "outgoing"
      ? outgoing
      : filters.direction === "incoming"
        ? incoming
        : // "both": dedupe self-loops that appear in both lists
          dedupeByClaim([...outgoing, ...incoming]);

  const allEligible = dedupeByClaim([...outgoing, ...incoming]);
  const totalEligible = allEligible.length;
  const allPredicates = [...new Set(allEligible.map((e) => e.predicate))].sort();
  const filtered = byDirection.filter((e) => matchesFilters(e, filters));
  const ordered = orderEdges(filtered, centerId);
  const shown = ordered.slice(0, cap);

  const neighborIds = new Set<string>();
  for (const e of shown) {
    neighborIds.add(e.source_node_id === centerId ? e.target_node_id : e.source_node_id);
  }
  const neighbors = [...neighborIds]
    .map((id) => index.nodeById.get(id))
    .filter((n): n is GraphNode => n !== undefined);

  const nonProjectable = dedupeNp(
    center.expressions.flatMap((form) => index.nonProjectableBySurface.get(form) ?? []),
  );

  return {
    center,
    edges: shown,
    neighbors,
    nonProjectable,
    allPredicates,
    counts: {
      displayed: shown.length,
      availableAfterFilter: filtered.length,
      totalEligible,
      hiddenByCap: filtered.length - shown.length,
      nonProjectable: nonProjectable.length,
    },
  };
};

const dedupeByClaim = (edges: GraphEdge[]): GraphEdge[] => {
  const seen = new Set<string>();
  const out: GraphEdge[] = [];
  for (const e of edges) {
    if (seen.has(e.claim_id)) continue;
    seen.add(e.claim_id);
    out.push(e);
  }
  return out;
};

const dedupeNp = (claims: NonProjectable[]): NonProjectable[] => {
  const seen = new Set<string>();
  const out: NonProjectable[] = [];
  for (const c of claims) {
    if (seen.has(c.claim_id)) continue;
    seen.add(c.claim_id);
    out.push(c);
  }
  return out.sort((a, b) => (a.claim_id < b.claim_id ? -1 : a.claim_id > b.claim_id ? 1 : 0));
};

// Search: match the query against node labels and observed expressions, case-insensitive.
// Distinct nodes stay distinct (never merged), ordered by label for a stable result.
export const searchNodes = (
  index: GraphIndex,
  query: string,
  limit = 25,
): GraphNode[] => {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const hits = index.artifact.nodes.filter(
    (n) =>
      n.label.toLowerCase().includes(q) ||
      n.expressions.some((e) => e.toLowerCase().includes(q)),
  );
  return hits
    .sort((a, b) => {
      // exact label match first, then shorter label, then lexicographic
      const ax = a.label.toLowerCase() === q ? 0 : 1;
      const bx = b.label.toLowerCase() === q ? 0 : 1;
      if (ax !== bx) return ax - bx;
      if (a.label.length !== b.label.length) return a.label.length - b.label.length;
      return a.label < b.label ? -1 : a.label > b.label ? 1 : 0;
    })
    .slice(0, limit);
};

// Resolve the passage an edge or non-projectable claim rests on, by its join key
// (source_id + evidence span) — both the claim record and the passage carry it.
export const passageForClaim = (
  index: GraphIndex,
  sourceId: string,
  start: number,
  end: number,
): PassageRef | undefined =>
  index.passageByKey.get(passageKey(sourceId, start, end));
