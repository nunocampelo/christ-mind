import type { CitedClaim } from "@/api/agentApi";

// Section numbers are small (single digits, occasionally low teens across the full Text),
// so the table only needs to cover tens.
const ROMAN: [number, string][] = [
  [10, "X"],
  [9, "IX"],
  [5, "V"],
  [4, "IV"],
  [1, "I"],
];

const toRoman = (n: number): string => {
  let remaining = n;
  let out = "";
  for (const [value, symbol] of ROMAN) {
    while (remaining >= value) {
      out += symbol;
      remaining -= value;
    }
  }
  return out;
};

// A reference split into the work and the location within it, so the UI can stack them
// ("A Course in Miracles" over "Chapter 1 Section I Paragraph 1"). `location` is empty when
// there's nothing to say beyond the title (e.g. the raw-id fallback).
export interface SourceReferenceParts {
  title: string;
  location: string;
}

// Turn a claim's structured location into a human reference. ACIM reads
// "A Course in Miracles" / "Chapter 3 Section IV Paragraph 25" (section 0 is the chapter
// Introduction); Bible reads "Matthew" / "5:7". The `edition` field is carried on the claim
// but intentionally not rendered yet. Anything without the fields we need falls back to the
// raw source_id so an unrecognized shape is still identifiable.
export const sourceReferenceParts = (claim: CitedClaim): SourceReferenceParts => {
  const { book, chapter, verse, section, paragraph } = claim;

  if (book && verse != null) {
    return { title: book, location: `${chapter}:${verse}` };
  }

  if (book === "ACIM" && chapter) {
    const sectionPart =
      section === 0 ? " Introduction" : section != null ? ` Section ${toRoman(section)}` : "";
    const paragraphPart = paragraph != null ? ` Paragraph ${paragraph}` : "";
    return {
      title: "A Course in Miracles",
      location: `Chapter ${chapter}${sectionPart}${paragraphPart}`.trim(),
    };
  }

  return { title: claim.source_id, location: "" };
};

export const sourceReference = (claim: CitedClaim): string => {
  const { title, location } = sourceReferenceParts(claim);
  return location ? `${title} ${location}` : title;
};
