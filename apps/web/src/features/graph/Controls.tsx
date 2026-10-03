import type { Predicate } from "@/api/graphArtifact";
import {
  type Direction,
  type GraphFilters,
  type NeighborhoodCounts,
} from "@/features/graph/graphModel";
import { cn } from "@/lib/cn";

const DIRECTIONS: { value: Direction; label: string }[] = [
  { value: "both", label: "Both" },
  { value: "incoming", label: "Incoming" },
  { value: "outgoing", label: "Outgoing" },
];

// Direction + predicate filters, and a counts line. Changing a filter recalculates counts
// in the parent; an empty filtered result shows explicitly as "0 of N", never as a blank
// that could be read as "the corpus knows nothing here".
const Controls = ({
  filters,
  availablePredicates,
  counts,
  canReset,
  onDirection,
  onTogglePredicate,
  onReset,
  onBack,
  canGoBack,
}: {
  filters: GraphFilters;
  availablePredicates: Predicate[];
  counts: NeighborhoodCounts;
  canReset: boolean;
  onDirection: (d: Direction) => void;
  onTogglePredicate: (p: Predicate) => void;
  onReset: () => void;
  onBack: () => void;
  canGoBack: boolean;
}) => (
  <div className="graph-controls" data-testid="controls">
    <div className="graph-control-row" role="group" aria-label="Direction">
      {DIRECTIONS.map((d) => (
        <button
          key={d.value}
          type="button"
          data-testid={`direction-${d.value}`}
          data-active={filters.direction === d.value}
          onClick={() => onDirection(d.value)}
          className={cn(
            "graph-chip",
            filters.direction === d.value && "graph-chip-active",
          )}
        >
          {d.label}
        </button>
      ))}
    </div>

    {availablePredicates.length > 0 && (
      <div className="graph-control-row" role="group" aria-label="Predicate filter">
        {availablePredicates.map((p) => {
          const on = filters.predicates.has(p);
          return (
            <button
              key={p}
              type="button"
              data-testid={`predicate-${p}`}
              data-active={on}
              aria-pressed={on}
              onClick={() => onTogglePredicate(p)}
              className={cn("graph-chip", on && "graph-chip-active")}
            >
              {p.replace(/_/g, " ")}
            </button>
          );
        })}
      </div>
    )}

    <div className="graph-control-row">
      <button
        type="button"
        data-testid="back"
        disabled={!canGoBack}
        onClick={onBack}
        className="graph-chip"
      >
        Previous
      </button>
      <button
        type="button"
        data-testid="reset"
        disabled={!canReset}
        onClick={onReset}
        className="graph-chip"
      >
        Reset
      </button>
    </div>

    <p className="graph-counts" data-testid="counts">
      Showing {counts.displayed} of {counts.availableAfterFilter} filtered
      {counts.hiddenByCap > 0 && ` (${counts.hiddenByCap} hidden by cap)`}
      {" · "}
      {counts.totalEligible} total eligible
      {counts.nonProjectable > 0 && ` · ${counts.nonProjectable} not drawable`}
    </p>
  </div>
);

export default Controls;
