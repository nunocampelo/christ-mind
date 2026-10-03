import { describe, expect, it } from "vitest";
import {
  buildIndex,
  defaultFilters,
  neighborhood,
  passageForClaim,
  searchNodes,
  type GraphFilters,
} from "@/features/graph/graphModel";
import type { Direction } from "@/features/graph/graphModel";
import { parseArtifact, ArtifactError, type Predicate } from "@/api/graphArtifact";
import { F, G, RM, makeArtifact } from "@/features/graph/fixture";

const index = () => buildIndex(makeArtifact());

const filters = (over: Partial<GraphFilters> = {}): GraphFilters => ({
  ...defaultFilters(),
  ...over,
});

describe("neighborhood", () => {
  it("returns null for an unknown center", () => {
    expect(neighborhood(index(), "m:nope", defaultFilters())).toBeNull();
  });

  it("keeps parallel edges between the same pair distinct", () => {
    const n = neighborhood(index(), F.node_id, defaultFilters())!;
    const toHealing = n.edges.filter((e) => e.target_node_id === "m:healing");
    expect(toHealing.map((e) => e.claim_id).sort()).toEqual([
      "c_causes",
      "c_causes_neg",
    ]);
  });

  it("dedupes a self-loop that is both incoming and outgoing", () => {
    const n = neighborhood(index(), F.node_id, filters({ direction: "both" }))!;
    const selfLoops = n.edges.filter((e) => e.claim_id === "c_self");
    expect(selfLoops).toHaveLength(1);
  });

  it("filters by direction, counting totalEligible against the unfiltered set", () => {
    const out = neighborhood(index(), F.node_id, filters({ direction: "outgoing" }))!;
    const inc = neighborhood(index(), F.node_id, filters({ direction: "incoming" }))!;
    // outgoing: c_causes, c_causes_neg, c_self (self-loop is outgoing too)
    expect(out.edges.map((e) => e.claim_id).sort()).toEqual([
      "c_causes",
      "c_causes_neg",
      "c_self",
    ]);
    // incoming: c_incoming (God→forgiveness) + c_self (self-loop)
    expect(inc.edges.map((e) => e.claim_id).sort()).toEqual(["c_incoming", "c_self"]);
    // totalEligible ignores the direction filter: the deduped union of in+out = 4.
    expect(out.counts.totalEligible).toBe(4);
    expect(inc.counts.totalEligible).toBe(4);
  });

  it("filters by predicate and reports available vs displayed", () => {
    const n = neighborhood(
      index(),
      F.node_id,
      filters({ predicates: new Set<Predicate>(["causes"]) }),
    )!;
    expect(n.edges.map((e) => e.claim_id)).toEqual(["c_causes"]);
    expect(n.counts.displayed).toBe(1);
    expect(n.counts.availableAfterFilter).toBe(1);
    expect(n.counts.totalEligible).toBe(4);
    expect(n.counts.hiddenByCap).toBe(0);
  });

  it("caps displayed edges and reports the hidden remainder", () => {
    const n = neighborhood(index(), F.node_id, defaultFilters(), 2)!;
    expect(n.counts.displayed).toBe(2);
    expect(n.counts.availableAfterFilter).toBe(4);
    expect(n.counts.hiddenByCap).toBe(2);
    expect(n.edges).toHaveLength(2);
  });

  it("surfaces non-projectable claims the center participates in", () => {
    const n = neighborhood(index(), F.node_id, defaultFilters())!;
    expect(n.nonProjectable.map((c) => c.claim_id)).toEqual(["np1"]);
    expect(n.counts.nonProjectable).toBe(1);
  });

  it("does not merge the endpoints of an `is` edge", () => {
    const n = neighborhood(index(), G.node_id, defaultFilters())!;
    const isEdge = n.edges.find((e) => e.predicate === "is")!;
    expect(isEdge.source_node_id).toBe(G.node_id);
    expect(isEdge.target_node_id).toBe(RM.node_id);
    expect(G.node_id).not.toEqual(RM.node_id);
    // Both endpoints remain distinct nodes in the index.
    expect(index().nodeById.get(RM.node_id)).toBeDefined();
  });

  it("exposes every eligible predicate, independent of the active filter and the cap", () => {
    const all = ["causes", "expresses", "requires", "undoes"];
    // no filter: all four predicates on forgiveness's eligible edges
    expect(neighborhood(index(), F.node_id, defaultFilters())!.allPredicates).toEqual(all);
    // a predicate filter must NOT narrow the options (else picking one hides the rest)
    const filtered = neighborhood(
      index(),
      F.node_id,
      filters({ predicates: new Set<Predicate>(["causes"]) }),
    )!;
    expect(filtered.allPredicates).toEqual(all);
    // and the cap must NOT narrow them (the "first N edges all share one predicate" case)
    const capped = neighborhood(index(), F.node_id, defaultFilters(), 1)!;
    expect(capped.edges).toHaveLength(1);
    expect(capped.allPredicates).toEqual(all);
  });

  it("orders edges deterministically (predicate, far endpoint, claim)", () => {
    const once = neighborhood(index(), F.node_id, defaultFilters())!.edges.map((e) => e.claim_id);
    const twice = neighborhood(index(), F.node_id, defaultFilters())!.edges.map((e) => e.claim_id);
    expect(once).toEqual(twice);
    // predicate asc: causes < requires < undoes
    const predicates = neighborhood(index(), F.node_id, filters({ direction: "outgoing" }))!.edges.map(
      (e) => e.predicate,
    );
    expect(predicates).toEqual([...predicates].sort());
  });
});

describe("searchNodes", () => {
  it("returns nothing for a blank query", () => {
    expect(searchNodes(index(), "   ")).toEqual([]);
  });

  it("matches on label and on observed expressions, case-insensitively", () => {
    const hits = searchNodes(index(), "FORGIVE").map((n) => n.node_id);
    expect(hits).toContain(F.node_id);
  });

  it("keeps ambiguous matches as distinct nodes, exact label first", () => {
    const hits = searchNodes(index(), "God");
    expect(hits[0].node_id).toBe(G.node_id); // exact label match ranks first
    // a broad substring returns multiple distinct nodes, never a merged one
    const many = searchNodes(index(), "i");
    const ids = new Set(many.map((n) => n.node_id));
    expect(ids.size).toBe(many.length);
  });
});

describe("passageForClaim", () => {
  it("joins an edge to its passage by (source_id, span)", () => {
    const p = passageForClaim(index(), "s1", 0, 10)!;
    expect(p.evidence.clause).toBe("forgiveness brings about healing");
  });

  it("returns undefined when no passage carries that span", () => {
    expect(passageForClaim(index(), "s1", 999, 1000)).toBeUndefined();
  });

  it("preserves non-BMP context verbatim without re-slicing on offsets", () => {
    const p = passageForClaim(index(), "s2", 5, 20)!;
    expect(p.evidence.before).toBe("👁 ");
    expect(p.evidence.clause).toBe("forgiveness undoes fear");
  });
});

describe("parseArtifact failures", () => {
  it("rejects an incompatible schema version", () => {
    const bad = { ...makeArtifact(), metadata: { ...makeArtifact().metadata, schema_version: "0.0.0" } };
    expect(() => parseArtifact(bad)).toThrow(ArtifactError);
  });

  it("rejects a non-object artifact", () => {
    expect(() => parseArtifact(null)).toThrow(ArtifactError);
  });

  it("round-trips a valid artifact through parse", () => {
    const art = makeArtifact();
    const parsed = parseArtifact(JSON.parse(JSON.stringify(art)));
    expect(parsed.edges.map((e) => e.claim_id)).toEqual(art.edges.map((e) => e.claim_id));
  });
});

// Exhaustive guard: a Direction union change should break here, flagging the model.
const _directions: Direction[] = ["both", "incoming", "outgoing"];
void _directions;
