import { describe, expect, it } from "vitest";
import { citedProseToPlainText, type CitedClaim } from "@/api/agentApi";

const claim = (over: Partial<CitedClaim>): CitedClaim => ({
  claim_id: "c1",
  source_id: "T-1.II.3",
  book: "",
  chapter: 0,
  verse: null,
  section: null,
  paragraph: null,
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

describe("citedProseToPlainText", () => {
  it("rewrites resolvable markers to their reader-facing ordinal", () => {
    const raw = "Forgiveness completed is the Atonement [abc]. Miracles express it [def].";
    const claims = [
      claim({ claim_id: "abc" }),
      claim({ claim_id: "def", source_id: "T-1.I.6" }),
    ];
    expect(citedProseToPlainText(raw, claims)).toBe(
      "Forgiveness completed is the Atonement [1]. Miracles express it [2].",
    );
  });

  it("drops an unresolvable marker and heals the stranded space", () => {
    const raw = "the opposite of love is fear [nope], and love is maximal.";
    expect(citedProseToPlainText(raw, [])).toBe(
      "the opposite of love is fear, and love is maximal.",
    );
  });

  it("leaves marker-free prose untouched", () => {
    expect(citedProseToPlainText("Plain prose, no markers.", [])).toBe(
      "Plain prose, no markers.",
    );
  });
});
