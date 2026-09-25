import type { AgentAnswer, CitedClaim } from "@/api/agentApi";
import MarkdownMessage from "@/components/chat/MarkdownMessage";
import "@/components/chat/chat.css";

interface CitedAnswerProps {
  answer: AgentAnswer;
  streamedText: string;
}

const claimGloss = (claim: CitedClaim): string =>
  claim.object === null
    ? `${claim.subject} ${claim.verb_phrase}`
    : `${claim.subject} ${claim.verb_phrase} ${claim.object}`;

const ClaimEvidence = ({ claim }: { claim: CitedClaim }) => (
  <div className="cited-claim" data-testid="cited-claim">
    <p className="cited-claim-gloss">{claimGloss(claim)}</p>
    <blockquote className="cited-claim-evidence">{claim.evidence}</blockquote>
    <span className="cited-source">{claim.source_id}</span>
  </div>
);

/** Renders an agent answer keeping the system invariant visible: what the Course
    *says* (cited claims, each with a source_id) stays distinct from what *follows*
    (inferred chains, marked inferred, whose links stay Course-attributed). Never one
    flat blob. */
const CitedAnswer = ({ answer, streamedText }: CitedAnswerProps) => (
  <div className="cited-answer">
    <MarkdownMessage text={streamedText || answer.text} />

    {answer.cited_claims.length > 0 && (
      <section className="cited-section" data-testid="cited-claims">
        <h3 className="cited-heading">The Course says</h3>
        {answer.cited_claims.map((claim) => (
          <ClaimEvidence key={claim.claim_id} claim={claim} />
        ))}
      </section>
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

export default CitedAnswer;
