import { useMemo } from "react";
import type {
  Attribution,
  GraphEdge,
  Mode,
  NonProjectable,
  Polarity,
  PassageRef,
} from "@/api/graphArtifact";
import { type GraphIndex, passageForClaim } from "@/features/graph/graphModel";
import { sourceReferenceParts } from "@/api/sourceRef";
import "@/components/chat/chat.css";

// A selected relationship, either a drawn edge or a non-projectable participating claim.
// Both carry the semantic fields + the join key the evidence panel needs.
export type Selection =
  | { kind: "edge"; edge: GraphEdge }
  | { kind: "non_projectable"; claim: NonProjectable };

// sourceReferenceParts reads only these fields; a passage supplies all of them. Reusing it
// keeps graph locators identical to the chat citations' ("A Course in Miracles" / "Chapter
// 1 Section I Paragraph 1", "Matthew" / "5:7", raw id fallback).
const referenceParts = (p: PassageRef) =>
  sourceReferenceParts({
    book: p.book,
    chapter: p.chapter,
    verse: p.verse,
    section: p.section,
    paragraph: p.paragraph,
    source_id: p.source_id,
  } as Parameters<typeof sourceReferenceParts>[0]);

const polarityLabel = (p: Polarity): string => (p === "negated" ? "Negated" : "");
const modeLabel = (m: Mode): string =>
  m === "assertion" ? "" : m.charAt(0).toUpperCase() + m.slice(1);
const attributionLabel = (a: Attribution): string =>
  a === "course" ? "" : `Attributed to ${a}`;

// Qualifier chips: polarity/mode/attribution shown as text, never only as styling, so a
// negated or ego-attributed claim can't be read as a flat Course assertion.
const Qualifiers = ({
  polarity,
  mode,
  attribution,
}: {
  polarity: Polarity;
  mode: Mode;
  attribution: Attribution;
}) => {
  const chips = [polarityLabel(polarity), modeLabel(mode), attributionLabel(attribution)].filter(
    Boolean,
  );
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
  const ref = passage ? referenceParts(passage) : null;

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
          {ref && (
            <span className="cited-source">
              <span className="cited-source-title">{ref.title}</span>
              {ref.location && <span className="cited-source-location">{ref.location}</span>}
            </span>
          )}
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
