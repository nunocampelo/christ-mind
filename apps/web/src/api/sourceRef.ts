import type { CitedClaim } from "@/api/agentApi";
import type { PassageRef } from "@/api/graphArtifact";

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

// The graph explorer's source locator. Discriminated on `kind` rather than a boolean: a
// boolean can't tell an ACIM import ordinal from an unknown-source fallback, and a
// populated verse field doesn't establish canonical validity on its own.
//
// ACIM locators are deliberately NOT rendered as canonical Chapter/Section/Paragraph
// citations: the numbers are positional block ordinals assigned at import (see
// docs/graph-explorer-inspection.md), so they surface as a stored location with the
// dataset edition and raw id, flagged as unverified. Bible verse refs are real citations.
export type GraphLocator =
  | { kind: "acim"; title: string; storedLocation: string; edition: string; id: string }
  | { kind: "verse"; title: string; location: string }
  | { kind: "fallback"; title: string };

export const graphSourceLocator = (p: PassageRef): GraphLocator => {
  if (p.book === "ACIM" && p.chapter) {
    const parts = [`Chapter ${p.chapter}`];
    if (p.section === 0) parts.push("Introduction");
    else if (p.section != null) parts.push(`Section ${p.section}`);
    if (p.paragraph != null) parts.push(`Block ${p.paragraph}`);
    return {
      kind: "acim",
      title: "A Course in Miracles",
      storedLocation: parts.join(" · "),
      edition: p.edition,
      id: p.source_id,
    };
  }

  if (p.book && p.verse != null) {
    return { kind: "verse", title: p.book, location: `${p.chapter}:${p.verse}` };
  }

  return { kind: "fallback", title: p.source_id };
};
