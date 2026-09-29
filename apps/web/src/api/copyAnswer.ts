import {
  citedProseToPlainText,
  parseCitedProse,
  type AgentAnswer,
  type CitedClaim,
} from "@/api/agentApi";
import { sourceReference } from "@/api/sourceRef";

// The source paragraph a claim was drawn from, with the evidence clause wrapped in ** so the
// reader can see where the citation lands within it. Falls back to the bare clause when the
// source paragraph couldn't be fetched (evidence_context === "").
const evidenceParagraph = (c: CitedClaim): string => {
  if (!c.evidence_context) return c.evidence;
  const before = c.evidence_context.slice(0, c.evidence_start);
  const marked = c.evidence_context.slice(c.evidence_start, c.evidence_end);
  const after = c.evidence_context.slice(c.evidence_end);
  return `${before}**${marked}**${after}`;
};

// The clipboard form of an agent answer: readable prose with inline [n] markers, a compact
// Sources list resolving them, and — kept visibly separate — the inferred chains, so copied
// text preserves the cited-vs-inferred boundary rather than making synthesis look sourced.
// No quotes, URLs, or internal ids; just the human reference (e.g. "T-4.I.1").
export const copyTextForAnswer = (answer: AgentAnswer): string => {
  const prose = citedProseToPlainText(answer.text, answer.cited_claims);

  const ordinals = new Map<string, number>();
  for (const seg of parseCitedProse(answer.text, answer.cited_claims)) {
    if (seg.kind === "citation" && seg.claim && !ordinals.has(seg.claim.claim_id)) {
      ordinals.set(seg.claim.claim_id, seg.ordinal);
    }
  }

  const cited = [...answer.cited_claims]
    .filter((c) => ordinals.has(c.claim_id))
    .sort((a, b) => ordinals.get(a.claim_id)! - ordinals.get(b.claim_id)!)
    .map(
      (c) =>
        `[${ordinals.get(c.claim_id)}] ${sourceReference(c)}\n${evidenceParagraph(c)}`,
    );

  const inferred = answer.inferred_chains.flatMap((chain) =>
    chain.links.map((link) => `— ${sourceReference(link)}`),
  );

  const blocks = [prose];
  if (cited.length) blocks.push(`Sources:\n${cited.join("\n\n")}`);
  if (inferred.length) blocks.push(`Inferred from:\n${inferred.join("\n")}`);
  return blocks.join("\n\n");
};
