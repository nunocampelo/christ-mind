import { useMemo } from "react";
import type {
  Attribution,
  GraphEdge,
  Mode,
  NonProjectable,
  Polarity,
} from "@/api/graphArtifact";
import { type GraphIndex, passageForClaim } from "@/features/graph/graphModel";
import { type GraphLocator, LocatorKind, graphSourceLocator } from "@/api/sourceRef";
import { qualifierLabels } from "@/features/graph/qualifiers";

// A selected relationship, either a drawn edge or a non-projectable participating claim.
// Both carry the semantic fields + the join key the evidence panel needs.
export const SelectionKind = {
  edge: "edge",
  nonProjectable: "non_projectable",
} as const;
export type SelectionKind = (typeof SelectionKind)[keyof typeof SelectionKind];

export type Selection =
  | { kind: typeof SelectionKind.edge; edge: GraphEdge }
  | { kind: typeof SelectionKind.nonProjectable; claim: NonProjectable };

// Qualifier chips: polarity/mode/attribution shown as text, never only as styling, so a
// negated or ego-attributed claim can't be read as a flat Course assertion. Wording comes
// from the shared helper so it matches the relationship list exactly.
const Qualifiers = ({
  polarity,
  mode,
  attribution,
}: {
  polarity: Polarity;
  mode: Mode;
  attribution: Attribution;
}) => {
  const chips = qualifierLabels(polarity, mode, attribution);
  if (chips.length === 0) return null;
  return (
    <div className="graph-qualifiers" data-testid="qualifiers">
      {chips.map((c) => (
        <span key={c} className="graph-qualifier">
          {c}
        </span>
      ))}
    </div>
  );
};

// Compact source reference beneath the passage, with a "Source details" disclosure for
// source metadata. ACIM numbers are positional block ordinals assigned at import, not the
// Course's canonical Principle/verse numbers (see docs/graph-explorer-inspection.md), so
// they carry an explicit "not a verified citation" caveat on the compact line and the
// dataset edition + raw id in the details. Bible verse refs are genuine citations. The
// details disclosure holds information about the SOURCE only — never why a claim is or
// isn't drawn in the graph.
const SourceReference = ({ locator }: { locator: GraphLocator }) => (
  <div className="graph-reader-ref" data-testid="source-reference">
    <span className="graph-reader-ref-compact">{locator.compact}</span>
    {locator.kind === LocatorKind.acim && (
      <span className="graph-reader-caveat">(stored location, not a verified citation)</span>
    )}
    {locator.kind !== LocatorKind.fallback && (
      <details className="graph-reader-details" data-testid="source-details">
        <summary>Source details</summary>
        {locator.kind === LocatorKind.acim ? (
          <span>
            Dataset edition: “{locator.edition}” · ID: <code>{locator.id}</code>
          </span>
        ) : (
          <span>
            ID: <code>{locator.id}</code>
          </span>
        )}
      </details>
    )}
  </div>
);

const EvidencePanel = ({
  selection,
  index,
}: {
  selection: Selection | null;
  index: GraphIndex;
}) => {
  const fields =
    selection === null
      ? null
      : selection.kind === SelectionKind.edge
        ? selection.edge
        : selection.claim;

  const passage = useMemo(() => {
    if (!fields) return undefined;
    return passageForClaim(index, fields.source_id, fields.evidence_start, fields.evidence_end);
  }, [fields, index]);

  if (!selection || !fields) {
    return (
      <aside className="graph-evidence graph-evidence-empty" data-testid="evidence-panel">
        <p className="graph-evidence-hint">
          Select a relationship to see exactly what the Course says.
        </p>
      </aside>
    );
  }

  const locator = passage ? graphSourceLocator(passage) : null;

  return (
    <aside className="graph-evidence" data-testid="evidence-panel">
      <Qualifiers
        polarity={fields.polarity}
        mode={fields.mode}
        attribution={fields.attribution}
      />
      {selection.kind === SelectionKind.nonProjectable && (
        <p className="graph-evidence-excluded" data-testid="exclusion-reason">
          Not shown in graph: {selection.claim.reason.replace(/_/g, " ")}
        </p>
      )}

      {passage ? (
        <>
          <blockquote className="graph-reader-passage" data-testid="passage">
            {passage.evidence.before}
            <mark className="graph-reader-clause" data-testid="passage-clause">
              {passage.evidence.clause}
            </mark>
            {passage.evidence.after}
          </blockquote>
          {locator && <SourceReference locator={locator} />}
        </>
      ) : (
        <p className="graph-evidence-hint" data-testid="evidence-missing">
          Evidence for this claim is unavailable in the current artifact.
        </p>
      )}
    </aside>
  );
};

export default EvidencePanel;
