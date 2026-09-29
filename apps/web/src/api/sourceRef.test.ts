import { describe, expect, it } from "vitest";
import type { CitedClaim } from "@/api/agentApi";
import { sourceReference, sourceReferenceParts } from "@/api/sourceRef";

const claim = (over: Partial<CitedClaim>): CitedClaim => ({
  claim_id: "c1",
  source_id: "raw-id",
  book: "",
  chapter: 0,
  verse: null,
  section: null,
  paragraph: null,
  edition: "",
  subject: "s",
  predicate: "p",
  object: null,
  verb_phrase: "v",
  polarity: "affirmed",
  evidence: "e",
  evidence_context: "",
  evidence_start: 0,
  evidence_end: 0,
  ...over,
});

describe("sourceReference", () => {
  it("formats an ACIM section as a roman numeral", () => {
    expect(
      sourceReference(claim({ book: "ACIM", chapter: 3, section: 4, paragraph: 25 })),
    ).toBe("A Course in Miracles Chapter 3 Section IV Paragraph 25");
  });

  it("renders section 0 as the chapter Introduction", () => {
    expect(
      sourceReference(claim({ book: "ACIM", chapter: 1, section: 0, paragraph: 1 })),
    ).toBe("A Course in Miracles Chapter 1 Introduction Paragraph 1");
  });

  it("formats a Bible reference as book chapter:verse", () => {
    expect(sourceReference(claim({ book: "Matthew", chapter: 5, verse: 7 }))).toBe(
      "Matthew 5:7",
    );
  });

  it("falls back to the raw source_id when location fields are absent", () => {
    expect(sourceReference(claim({ source_id: "T-1.II.3" }))).toBe("T-1.II.3");
  });
});

describe("sourceReferenceParts", () => {
  it("splits an ACIM reference into title and location", () => {
    expect(
      sourceReferenceParts(claim({ book: "ACIM", chapter: 3, section: 4, paragraph: 25 })),
    ).toEqual({
      title: "A Course in Miracles",
      location: "Chapter 3 Section IV Paragraph 25",
    });
  });

  it("splits a Bible reference into book and chapter:verse", () => {
    expect(sourceReferenceParts(claim({ book: "Matthew", chapter: 5, verse: 7 }))).toEqual({
      title: "Matthew",
      location: "5:7",
    });
  });

  it("leaves location empty for the raw-id fallback", () => {
    expect(sourceReferenceParts(claim({ source_id: "T-1.II.3" }))).toEqual({
      title: "T-1.II.3",
      location: "",
    });
  });
});
