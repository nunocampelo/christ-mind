import type { AgentAnswer, CitedClaim } from "@/api/agentApi";
import { parseCitedProse } from "@/api/agentApi";
import MarkdownMessage from "@/components/chat/MarkdownMessage";
import "@/components/chat/chat.css";

interface CitedAnswerProps {
  answer: AgentAnswer;
  streamedText: string;
}

// A negated claim reads affirmative as subject-verb-object ("God is partial") while its
// evidence says the opposite ("God is NOT partial"). Flag it so the gloss can't contradict
// the quote shown right beneath it.
const claimGloss = (claim: CitedClaim): string => {
  const core =
    claim.object === null
      ? `${claim.subject} ${claim.verb_phrase}`
      : `${claim.subject} ${claim.verb_phrase} ${claim.object}`;
  return claim.polarity === "negated" ? `Not: ${core}` : core;
};

const sourceAnchor = (claimId: string): string => `src-${claimId}`;

// One evidence unit: gloss + quote + source id, addressable by anchor so an inline
// superscript can jump to it. Rendered inside the Sources panel now; the same
// {claim, ordinal} shape is what a future click-popover would consume, so moving to a
// popover is a presentation change, not a contract change.
const ClaimEvidence = ({
  claim,
  ordinal,
}: {
  claim: CitedClaim;
  ordinal?: number;
}) => (
  <div className="cited-claim" id={sourceAnchor(claim.claim_id)} data-testid="cited-claim">
    {ordinal !== undefined && <span className="cited-ordinal">{ordinal}</span>}
    <p className="cited-claim-gloss">{claimGloss(claim)}</p>
    <blockquote className="cited-claim-evidence">{claim.evidence}</blockquote>
    <span className="cited-source">{claim.source_id}</span>
  </div>
);

/** The grounded prose with inline citation superscripts. Markers resolve to gathered
    claims; an unknown/malformed marker is dropped rather than shown as literal "[...]".
    With no resolvable marker the prose renders as ordinary markdown; once a marker
    resolves, segments render inline so the superscript sits mid-sentence rather than
    breaking the flow into blocks. */
const CitedProse = ({ answer }: { answer: AgentAnswer }) => {
  const segments = parseCitedProse(answer.text, answer.cited_claims);
  const hasCitation = segments.some((seg) => seg.kind === "citation");

  if (!hasCitation) return <MarkdownMessage text={answer.text} />;

  return (
    <div className="agent-markdown cited-prose">
      {segments.map((seg, i) =>
        seg.kind === "text" ? (
          <span key={i}>{seg.text}</span>
        ) : (
          <a
            key={i}
            className="cited-marker"
            href={`#${sourceAnchor(seg.claim.claim_id)}`}
            aria-label={`Source ${seg.ordinal}`}
          >
            {seg.ordinal}
          </a>
        ),
      )}
    </div>
  );
};

/** Renders an agent answer keeping the system invariant visible: what the Course
    *says* (cited claims, each with a source_id) stays distinct from what *follows*
    (inferred chains, marked inferred, whose links stay Course-attributed). The evidence
    machinery sits in a collapsed "Sources" panel; the prose itself reads directly, with
    citations as superscripts rather than narrated. */
const CitedAnswer = ({ answer, streamedText }: CitedAnswerProps) => {
  // While prose streams (before the structured evidence artifact lands) markers may be
  // partial, so render the raw stream. Once `answer.text` is present, resolve markers.
  const streaming = streamedText.length > 0 && answer.text.length === 0;
  const ordinals = new Map<string, number>();
  for (const seg of parseCitedProse(answer.text, answer.cited_claims)) {
    if (seg.kind === "citation" && !ordinals.has(seg.claim.claim_id)) {
      ordinals.set(seg.claim.claim_id, seg.ordinal);
    }
  }

  // Show sources in the order the prose cites them ([1], [2], ...), not retrieval order,
  // so the panel's numbering reads in sequence. Uncited claims (no ordinal) fall to the
  // end in their original order.
  const UNCITED = Number.MAX_SAFE_INTEGER;
  const sortedClaims = [...answer.cited_claims].sort(
    (a, b) =>
      (ordinals.get(a.claim_id) ?? UNCITED) - (ordinals.get(b.claim_id) ?? UNCITED),
  );

  return (
    <div className="cited-answer">
      {streaming ? (
        <MarkdownMessage text={streamedText} />
      ) : (
        <CitedProse answer={answer} />
      )}

      {answer.cited_claims.length > 0 && (
        <details className="cited-section" data-testid="cited-claims">
          <summary className="cited-heading">Sources</summary>
          {sortedClaims.map((claim) => (
            <ClaimEvidence
              key={claim.claim_id}
              claim={claim}
              ordinal={ordinals.get(claim.claim_id)}
            />
          ))}
        </details>
      )}

      {answer.inferred_chains.length > 0 && (
        <section className="inferred-section" data-testid="inferred-chains">
          <h3 className="inferred-heading">
            What follows <span className="inferred-badge">Inferred</span>
          </h3>
          {answer.inferred_chains.map((chain, i) => (
            <ol key={i} className="inferred-chain" data-testid="inferred-chain">
              {chain.links.map((link, j) => (
                <li key={`${link.claim_id}-${j}`} className="inferred-link">
                  <span className="inferred-link-gloss">{claimGloss(link)}</span>
                  <span className="cited-source">{link.source_id}</span>
                </li>
              ))}
            </ol>
          ))}
        </section>
      )}
    </div>
  );
};

export default CitedAnswer;
