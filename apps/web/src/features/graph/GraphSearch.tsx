import { useState } from "react";
import type { GraphNode } from "@/api/graphArtifact";
import { type GraphIndex, searchNodes } from "@/features/graph/graphModel";

// Three inspection starting points (plan 0030). Resolved against the live index at render,
// so a label that isn't in the artifact simply doesn't offer that shortcut rather than
// linking to a dead node.
const STARTING_POINTS = ["forgiveness", "right-mindedness", "God"];

const GraphSearch = ({
  index,
  onPick,
}: {
  index: GraphIndex;
  onPick: (node: GraphNode) => void;
}) => {
  const [query, setQuery] = useState("");
  const results = searchNodes(index, query);

  const starts = STARTING_POINTS.map((label) =>
    index.artifact.nodes.find(
      (n) => n.label.toLowerCase() === label.toLowerCase(),
    ),
  ).filter((n): n is GraphNode => n !== undefined);

  return (
    <div className="graph-search" data-testid="graph-search">
      <input
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search a concept…"
        aria-label="Search concepts"
        data-testid="search-input"
        className="graph-search-input"
      />

      {query.trim() === "" ? (
        <div className="graph-starts" data-testid="starting-points">
          <p className="graph-rel-subhead">Start from</p>
          {starts.map((n) => (
            <button
              key={n.node_id}
              type="button"
              data-testid="starting-point"
              onClick={() => onPick(n)}
              className="graph-chip"
            >
              {n.label}
            </button>
          ))}
        </div>
      ) : results.length === 0 ? (
        <p className="graph-search-empty" data-testid="search-empty">
          No concept matches “{query.trim()}”. The corpus may still discuss it under a
          different expression.
        </p>
      ) : (
        <ul className="graph-search-results" data-testid="search-results">
          {results.map((n) => (
            <li key={n.node_id}>
              <button
                type="button"
                data-testid="search-result"
                onClick={() => onPick(n)}
                className="graph-rel-item"
              >
                <span className="graph-rel-text">{n.label}</span>
                {n.expressions.length > 1 && (
                  <span className="graph-rel-far">{n.expressions.length} forms</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default GraphSearch;
