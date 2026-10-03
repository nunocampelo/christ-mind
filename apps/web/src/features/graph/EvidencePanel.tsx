import { useMemo } from "react";
import type {
  Attribution,
  GraphEdge,
  Mode,
  NonProjectable,
  Polarity,
} from "@/api/graphArtifact";
import { type GraphIndex, passageForClaim } from "@/features/graph/graphModel";
import { type GraphLocator, graphSourceLocator } from "@/api/sourceRef";
import { qualifierLabels } from "@/features/graph/qualifiers";
import "@/components/chat/chat.css";

// A selected relationship, either a drawn edge or a non-projectable participating claim.
// Both carry the semantic fields + the join key the evidence panel needs.
export type Selection =
  | { kind: "edge"; edge: GraphEdge }
  | { kind: "non_projectable"; claim: NonProjectable };

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

// Source locator. ACIM numbers are positional block ordinals assigned at import, not the
// Course's canonical Principle/verse numbers (see docs/graph-explorer-inspection.md), so
// they're labelled as a stored location with the dataset edition and raw id, and marked as
// not a verified citation — never rendered as a plain Chapter/Section/Paragraph reference
// that would imply bibliographic certainty. Bible verse refs are genuine citations.
const SourceLocator = ({ locator }: { locator: GraphLocator }) => {
  if (locator.kind === "acim") {
    return (
      <div className="graph-evidence-locator" data-testid="source-locator">
        <span className="graph-evidence-locator-title">{locator.title}</span>
        <span className="graph-evidence-locator-stored">
          Stored location: {locator.storedLocation}
        </span>
        <span className="graph-evidence-locator-edition">
          Dataset edition: “{locator.edition}” · ID: <code>{locator.id}</code>
        </span>
        <span className="graph-evidence-locator-disclaimer">
          Not a verified canonical citation.
        </span>
      </div>
    );
  }
  if (locator.kind === "verse") {
    return (
      <span className="graph-evidence-locator" data-testid="source-locator">
        <span className="graph-evidence-locator-title">{locator.title}</span>
        <span className="graph-evidence-locator-stored">{locator.location}</span>
      </span>
    );
  }
  return (
    <span className="graph-evidence-locator" data-testid="source-locator">
      <span className="graph-evidence-locator-title">{locator.title}</span>
    </span>
  );
};

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
      : selection.kind === "edge"
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

  const object = fields.object;
  const gloss =
    object === null
      ? `${fields.subject} ${fields.verb_phrase}`
      : `${fields.subject} ${fields.verb_phrase} ${object}`;
  const locator = passage ? graphSourceLocator(passage) : null;

  return (
    <aside className="graph-evidence" data-testid="evidence-panel">
      <p className="graph-evidence-gloss">
        {fields.polarity === "negated" ? `Not: ${gloss}` : gloss}
      </p>
      <Qualifiers
        polarity={fields.polarity}
        mode={fields.mode}
        attribution={fields.attribution}
      />
      {selection.kind === "non_projectable" && (
        <p className="graph-evidence-excluded" data-testid="exclusion-reason">
          Not drawn as an edge: {selection.claim.reason.replace(/_/g, " ")}
        </p>
      )}

      {passage ? (
        <>
          <blockquote className="cited-claim-evidence" data-testid="evidence-clause">
            {passage.evidence.clause}
          </blockquote>
          <details className="cited-context" data-testid="evidence-context">
            <summary className="cited-context-toggle">Show in context</summary>
            <blockquote className="cited-context-passage">
              {passage.evidence.before}
              <mark className="cited-context-clause">{passage.evidence.clause}</mark>
              {passage.evidence.after}
            </blockquote>
          </details>
          {locator && <SourceLocator locator={locator} />}
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
