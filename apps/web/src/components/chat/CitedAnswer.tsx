import type { AgentAnswer, CitedClaim } from "@/api/agentApi";
import { parseCitedProse } from "@/api/agentApi";
import { sourceReferenceParts } from "@/api/sourceRef";
import MarkdownMessage from "@/components/chat/MarkdownMessage";
import "@/components/chat/chat.css";

interface CitedAnswerProps {
  answer: AgentAnswer;
  streamedText: string;
  // Distinct per chat turn: the anchor id namespaces on it so a marker resolves to *this*
  // message's source, not the first same-claim_id element on the page (claim ids repeat
  // across turns). Defaults keep standalone renders / tests working.
  turnId?: number;
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

const sourceAnchor = (turnId: number, claimId: string): string =>
  `src-${turnId}-${claimId}`;

// Reveal the source in its collapsed panel, then ease it into view centered rather than
// letting the native #hash jump snap it to the container top. block:"center" keeps the
// abrupt edge-landing away; smoothness yields to prefers-reduced-motion.
const jumpToSource = (anchorId: string) => {
  const el = document.getElementById(anchorId);
  if (!el) return;
  el.closest("details")?.setAttribute("open", "");
  const reduce = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
};

// The reference pill: work title over location ("A Course in Miracles" / "Chapter 1
// Section I Paragraph 1"). Location is dropped when there's nothing beyond the title.
const SourceRef = ({ claim }: { claim: CitedClaim }) => {
  const { title, location } = sourceReferenceParts(claim);
  return (
    <span className="cited-source">
      <span className="cited-source-title">{title}</span>
      {location && <span className="cited-source-location">{location}</span>}
    </span>
  );
};

// The source paragraph split around the evidence clause, so the clause can be marked in
// place. Offsets index evidence_context; if they don't anchor the clause (missing context,
// or an older payload without offsets) we return null and the caller shows no context toggle
// rather than highlighting the wrong span. The backend already fails loud on a genuine
// offset/text mismatch, so a mismatch here means the fields simply aren't present.
const clauseInContext = (
  claim: CitedClaim,
): { before: string; clause: string; after: string } | null => {
  const context = claim.evidence_context;
  if (!context) return null;
  const { evidence_start: start, evidence_end: end } = claim;
  if (context.slice(start, end) !== claim.evidence) return null;
  return {
    before: context.slice(0, start),
    clause: context.slice(start, end),
    after: context.slice(end),
  };
};

// One evidence unit: gloss + quote + source id, addressable by anchor so an inline
// superscript can jump to it. When the claim carries its source paragraph, a "Show in
// context" toggle expands it beneath the quote with the clause marked in place -- the clause
// stays the citation, the paragraph is context for reading it (resolves references the bare
// clause can't carry). Rendered inside the Sources panel now; the same {claim, ordinal} shape
// is what a future click-popover would consume, so moving to a popover is a presentation
// change, not a contract change.
const ClaimEvidence = ({
  claim,
  ordinal,
  turnId,
}: {
  claim: CitedClaim;
  ordinal?: number;
  turnId: number;
}) => {
  const context = clauseInContext(claim);
  return (
    <div
      className="cited-claim"
      id={sourceAnchor(turnId, claim.claim_id)}
      data-testid="cited-claim"
    >
      {ordinal !== undefined && <span className="cited-ordinal">{ordinal}</span>}
      <div className="cited-claim-body">
        <p className="cited-claim-gloss">{claimGloss(claim)}</p>
        <blockquote className="cited-claim-evidence">{claim.evidence}</blockquote>
        {context && (
          <details className="cited-context" data-testid="cited-context">
            <summary className="cited-context-toggle">Show in context</summary>
            <blockquote className="cited-context-passage">
              {context.before}
              <mark className="cited-context-clause">{context.clause}</mark>
              {context.after}
            </blockquote>
          </details>
        )}
        <SourceRef claim={claim} />
      </div>
    </div>
  );
};

/** The grounded prose with inline citation superscripts. Markers resolve to gathered
    claims; an unknown/malformed marker is dropped rather than shown as literal "[...]".
    With no resolvable marker the prose renders as ordinary markdown; once a marker
    resolves, segments render inline so the superscript sits mid-sentence rather than
    breaking the flow into blocks.

    `pending` is set while the prose still streams (the evidence artifact hasn't landed):
    the superscript renders immediately, numbered by appearance, but as a bare <sup> with
    no source anchor to jump to yet -- it becomes a link once its claim resolves. */
const CitedProse = ({
  text,
  claims,
  turnId,
  pending = false,
}: {
  text: string;
  claims: CitedClaim[];
  turnId: number;
  pending?: boolean;
}) => {
  const segments = parseCitedProse(text, claims, pending);
  const hasCitation = segments.some((seg) => seg.kind === "citation");

  if (!hasCitation) return <MarkdownMessage text={text} />;

  return (
    <div className="agent-markdown cited-prose">
      {segments.map((seg, i) => {
        if (seg.kind === "text") return <span key={i}>{seg.text}</span>;
        if (!seg.claim)
          return (
            <sup key={i} className="cited-marker cited-marker-pending" aria-hidden="true">
              {seg.ordinal}
            </sup>
          );
        const anchor = sourceAnchor(turnId, seg.claim.claim_id);
        return (
          <a
            key={i}
            className="cited-marker"
            href={`#${anchor}`}
            aria-label={`Source ${seg.ordinal}`}
            onClick={(e) => {
              e.preventDefault();
              jumpToSource(anchor);
            }}
          >
            {seg.ordinal}
          </a>
        );
      })}
    </div>
  );
};

/** Renders an agent answer keeping the system invariant visible: what the Course
    *says* (cited claims, each with a source_id) stays distinct from what *follows*
    (inferred chains, marked inferred, whose links stay Course-attributed). The evidence
    machinery sits in a collapsed "Sources" panel; the prose itself reads directly, with
    citations as superscripts rather than narrated. */
const CitedAnswer = ({ answer, streamedText, turnId = 0 }: CitedAnswerProps) => {
  // While prose streams (before the structured evidence artifact lands) the claims aren't
  // known yet, so markers render as bare numbered superscripts (pending). Once `answer.text`
  // is present the same markers resolve to claims and the superscripts become source links.
  const streaming = streamedText.length > 0 && answer.text.length === 0;
  const ordinals = new Map<string, number>();
  for (const seg of parseCitedProse(answer.text, answer.cited_claims)) {
    if (seg.kind === "citation" && seg.claim && !ordinals.has(seg.claim.claim_id)) {
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
        <CitedProse text={streamedText} claims={[]} turnId={turnId} pending />
      ) : (
        <CitedProse text={answer.text} claims={answer.cited_claims} turnId={turnId} />
      )}

      {answer.cited_claims.length > 0 && (
        <details className="cited-section" data-testid="cited-claims">
          <summary className="cited-heading">Sources</summary>
          {sortedClaims.map((claim) => (
            <ClaimEvidence
              key={claim.claim_id}
              claim={claim}
              ordinal={ordinals.get(claim.claim_id)}
              turnId={turnId}
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
                  <SourceRef claim={link} />
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
