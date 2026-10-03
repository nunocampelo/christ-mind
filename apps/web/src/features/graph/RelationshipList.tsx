import type { GraphEdge, NonProjectable } from "@/api/graphArtifact";
import { type GraphIndex, type Neighborhood } from "@/features/graph/graphModel";
import type { Selection } from "@/features/graph/EvidencePanel";
import { cn } from "@/lib/cn";

// The relationship list: the same connections the canvas draws, as readable directed text,
// plus a clearly separated list of participating claims that cannot be drawn. Keyboard- and
// click-selectable; selecting opens the same evidence panel as a canvas edge.

const directionArrow = (edge: GraphEdge, centerId: string): string =>
  edge.source_node_id === centerId ? "→" : "←"; // outgoing → / incoming ←

const edgeText = (edge: GraphEdge): string =>
  edge.polarity === "negated"
    ? `${edge.subject} ${edge.verb_phrase} ${edge.object} (negated)`
    : `${edge.subject} ${edge.verb_phrase} ${edge.object}`;

const sel = (selection: Selection | null): string | null =>
  selection?.kind === "edge"
    ? selection.edge.claim_id
    : selection?.kind === "non_projectable"
      ? selection.claim.claim_id
      : null;

const RelationshipList = ({
  neighborhood,
  index,
  selection,
  onSelect,
}: {
  neighborhood: Neighborhood;
  index: GraphIndex;
  selection: Selection | null;
  onSelect: (s: Selection) => void;
}) => {
  const selectedId = sel(selection);
  const centerId = neighborhood.center.node_id;

  return (
    <div className="graph-rel-list" data-testid="relationship-list">
      <ul className="graph-rel-group" aria-label="Drawn relationships">
        {neighborhood.edges.map((edge) => {
          const far = index.nodeById.get(
            edge.source_node_id === centerId ? edge.target_node_id : edge.source_node_id,
          );
          return (
            <li key={edge.claim_id}>
              <button
                type="button"
                data-testid="rel-edge"
                data-active={edge.claim_id === selectedId}
                aria-current={edge.claim_id === selectedId}
                onClick={() => onSelect({ kind: "edge", edge })}
                className={cn(
                  "graph-rel-item",
                  edge.claim_id === selectedId && "graph-rel-item-active",
                )}
              >
                <span className="graph-rel-arrow" aria-hidden="true">
                  {directionArrow(edge, centerId)}
                </span>
                <span className="graph-rel-text">{edgeText(edge)}</span>
                {far && <span className="graph-rel-far">{far.label}</span>}
              </button>
            </li>
          );
        })}
      </ul>

      {neighborhood.nonProjectable.length > 0 && (
        <div className="graph-rel-nonprojectable" data-testid="nonprojectable-list">
          <p className="graph-rel-subhead">
            Participating claims not shown as edges ({neighborhood.nonProjectable.length})
          </p>
          <ul className="graph-rel-group">
            {neighborhood.nonProjectable.map((claim: NonProjectable) => (
              <li key={claim.claim_id}>
                <button
                  type="button"
                  data-testid="rel-nonprojectable"
                  data-active={claim.claim_id === selectedId}
                  aria-current={claim.claim_id === selectedId}
                  onClick={() => onSelect({ kind: "non_projectable", claim })}
                  className={cn(
                    "graph-rel-item graph-rel-item-muted",
                    claim.claim_id === selectedId && "graph-rel-item-active",
                  )}
                >
                  <span className="graph-rel-text">
                    {claim.subject} {claim.verb_phrase}
                    {claim.object ? ` ${claim.object}` : ""}
                  </span>
                  <span className="graph-rel-reason">{claim.reason.replace(/_/g, " ")}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default RelationshipList;
