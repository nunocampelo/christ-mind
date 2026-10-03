import { useEffect, useMemo, useState } from "react";
import {
  type GraphArtifact,
  type GraphNode,
  type Predicate,
  loadArtifact,
} from "@/api/graphArtifact";
import {
  type Direction,
  type GraphFilters,
  buildIndex,
  defaultFilters,
  neighborhood,
} from "@/features/graph/graphModel";
import type { Selection } from "@/features/graph/EvidencePanel";
import EvidencePanel from "@/features/graph/EvidencePanel";
import Controls from "@/features/graph/Controls";
import GraphCanvas from "@/features/graph/GraphCanvas";
import GraphSearch from "@/features/graph/GraphSearch";
import RelationshipList from "@/features/graph/RelationshipList";
import "@/features/graph/graph.css";

type Load =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; artifact: GraphArtifact };

// One entry in the view history, so Previous restores center + filters together.
interface ViewState {
  centerId: string;
  filters: GraphFilters;
}

const cloneFilters = (f: GraphFilters): GraphFilters => ({
  direction: f.direction,
  predicates: new Set(f.predicates),
});

const GraphPage = ({
  load = loadArtifact,
}: {
  load?: typeof loadArtifact;
}) => {
  const [state, setState] = useState<Load>({ status: "loading" });
  const [history, setHistory] = useState<ViewState[]>([]);
  const [selection, setSelection] = useState<Selection | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const artifact = await load();
        if (active) setState({ status: "ready", artifact });
      } catch (e) {
        if (active)
          setState({
            status: "error",
            message: e instanceof Error ? e.message : "artifact could not be loaded",
          });
      }
    })();
    return () => {
      active = false;
    };
  }, [load]);

  const index = useMemo(
    () => (state.status === "ready" ? buildIndex(state.artifact) : null),
    [state],
  );

  const current = history.length > 0 ? history[history.length - 1] : null;
  const view = useMemo(() => {
    if (!index || !current) return null;
    return neighborhood(index, current.centerId, current.filters);
  }, [index, current]);

  const pickNode = (node: GraphNode) => {
    setHistory([{ centerId: node.node_id, filters: defaultFilters() }]);
    setSelection(null);
  };

  const pushView = (next: ViewState) => {
    setHistory((h) => [...h, next]);
    setSelection(null);
  };

  const replaceFilters = (mut: (f: GraphFilters) => GraphFilters) => {
    setHistory((h) => {
      if (h.length === 0) return h;
      const top = h[h.length - 1];
      const next = { centerId: top.centerId, filters: mut(cloneFilters(top.filters)) };
      return [...h.slice(0, -1), next];
    });
  };

  const onDirection = (d: Direction) =>
    replaceFilters((f) => ({ ...f, direction: d }));
  const onTogglePredicate = (p: Predicate) =>
    replaceFilters((f) => {
      const preds = new Set(f.predicates);
      if (preds.has(p)) preds.delete(p);
      else preds.add(p);
      return { ...f, predicates: preds };
    });
  const onReset = () => {
    if (current) setHistory([{ centerId: current.centerId, filters: defaultFilters() }]);
    setSelection(null);
  };
  const onBack = () => {
    setHistory((h) => (h.length > 1 ? h.slice(0, -1) : h));
    setSelection(null);
  };
  const expandNeighbor = (nodeId: string) => {
    if (current) pushView({ centerId: nodeId, filters: cloneFilters(current.filters) });
  };

  if (state.status === "loading") {
    return (
      <div className="graph-page graph-state" data-testid="graph-loading">
        Loading the Course graph…
      </div>
    );
  }
  if (state.status === "error" || !index) {
    return (
      <div className="graph-page graph-state" data-testid="graph-error">
        <p>The graph could not be loaded.</p>
        {state.status === "error" && <p className="graph-state-detail">{state.message}</p>}
      </div>
    );
  }

  // every predicate on the current center's eligible edges (pre-filter, pre-cap), for the
  // filter row — so picking one predicate doesn't hide the others.
  const availablePredicates: Predicate[] = view ? view.allPredicates : [];

  return (
    <div className="graph-page" data-testid="graph-page">
      <div className="graph-left">
        <GraphSearch index={index} onPick={pickNode} />
        {view && (
          <RelationshipList
            neighborhood={view}
            index={index}
            selection={selection}
            onSelect={setSelection}
          />
        )}
      </div>

      <div className="graph-center">
        {!view ? (
          <div className="graph-state" data-testid="graph-no-selection">
            Search a concept or pick a starting point to explore its relationships.
          </div>
        ) : view.counts.totalEligible === 0 ? (
          <div className="graph-state" data-testid="graph-no-relationships">
            <p>
              No drawable relationships for <strong>{view.center.label}</strong> in this
              projection.
            </p>
            {view.counts.nonProjectable > 0 && (
              <p className="graph-state-detail">
                {view.counts.nonProjectable} participating claim
                {view.counts.nonProjectable === 1 ? "" : "s"} appear in the list on the
                left.
              </p>
            )}
          </div>
        ) : (
          <>
            <Controls
              filters={current!.filters}
              availablePredicates={availablePredicates}
              counts={view.counts}
              canReset={
                current!.filters.direction !== "both" ||
                current!.filters.predicates.size > 0
              }
              canGoBack={history.length > 1}
              onDirection={onDirection}
              onTogglePredicate={onTogglePredicate}
              onReset={onReset}
              onBack={onBack}
            />
            <GraphCanvas
              neighborhood={view}
              index={index}
              selection={selection}
              onSelectEdge={(claimId) => {
                const edge = view.edges.find((e) => e.claim_id === claimId);
                if (edge) setSelection({ kind: "edge", edge });
              }}
            />
            <div className="graph-expand" data-testid="expand-row">
              {view.neighbors.map((n) => (
                <button
                  key={n.node_id}
                  type="button"
                  data-testid="expand-neighbor"
                  onClick={() => expandNeighbor(n.node_id)}
                  className="graph-chip"
                >
                  Explore {n.label} →
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      <EvidencePanel selection={selection} index={index} />
    </div>
  );
};

export default GraphPage;
