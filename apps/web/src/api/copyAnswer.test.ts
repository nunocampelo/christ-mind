import { describe, expect, it } from "vitest";
import type { AgentAnswer, CitedClaim } from "@/api/agentApi";
import { copyTextForAnswer } from "@/api/copyAnswer";

const claim = (over: Partial<CitedClaim>): CitedClaim => ({
  claim_id: "c1",
  source_id: "T-1.II.3",
  book: "ACIM",
  chapter: 4,
  verse: null,
  section: 1,
  paragraph: 1,
  edition: "",
  subject: "s",
  predicate: "p",
  object: null,
  verb_phrase: "vp",
  polarity: "affirmed",
  evidence: "e",
  evidence_context: "",
  evidence_start: 0,
  evidence_end: 0,
  ...over,
});

describe("copyTextForAnswer", () => {
  it("appends a compact Sources list numbered to match the inline markers", () => {
    const answer: AgentAnswer = {
      text: "Separation is an illusion [a]. Miracles express forgiveness [b].",
      concepts: [],
      cited_claims: [
        claim({ claim_id: "a", chapter: 4, section: 1, paragraph: 1, evidence: "e1" }),
        claim({ claim_id: "b", chapter: 5, section: 2, paragraph: 4, evidence: "e2" }),
      ],
      inferred_chains: [],
    };
    expect(copyTextForAnswer(answer)).toBe(
      "Separation is an illusion [1]. Miracles express forgiveness [2].\n\n" +
        "Sources:\n" +
        "[1] A Course in Miracles Chapter 4 Section I Paragraph 1\ne1\n\n" +
        "[2] A Course in Miracles Chapter 5 Section II Paragraph 4\ne2",
    );
  });

  it("includes the source paragraph with the evidence clause marked", () => {
    const answer: AgentAnswer = {
      text: "Knowledge is timeless [a].",
      concepts: [],
      cited_claims: [
        claim({
          claim_id: "a",
          chapter: 3,
          section: 4,
          paragraph: 3,
          evidence: "Knowledge is timeless",
          evidence_context: "In fact, Knowledge is timeless, as its stability is beyond time.",
          evidence_start: 9,
          evidence_end: 30,
        }),
      ],
      inferred_chains: [],
    };
    expect(copyTextForAnswer(answer)).toBe(
      "Knowledge is timeless [1].\n\n" +
        "Sources:\n" +
        "[1] A Course in Miracles Chapter 3 Section IV Paragraph 3\n" +
        "In fact, **Knowledge is timeless**, as its stability is beyond time.",
    );
  });

  it("keeps inferred chains in their own labelled section", () => {
    const answer: AgentAnswer = {
      text: "Separation is an illusion [a].",
      concepts: [],
      cited_claims: [claim({ claim_id: "a", chapter: 4, section: 1, paragraph: 1 })],
      inferred_chains: [
        { inferred: true, links: [claim({ claim_id: "x", chapter: 6, section: 3, paragraph: 2 })] },
      ],
    };
    const out = copyTextForAnswer(answer);
    expect(out).toContain("Sources:\n[1] A Course in Miracles Chapter 4 Section I Paragraph 1");
    expect(out).toContain("Inferred from:\n— A Course in Miracles Chapter 6 Section III Paragraph 2");
  });

  it("omits the Sources block when nothing is cited", () => {
    const answer: AgentAnswer = {
      text: "A plain synthesis with no citations.",
      concepts: [],
      cited_claims: [],
      inferred_chains: [],
    };
    expect(copyTextForAnswer(answer)).toBe("A plain synthesis with no citations.");
  });
});
