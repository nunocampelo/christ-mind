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
// populated verse field doesn't establish canonical validity on its own. `compact` is the
// one-line reference the reader shows; `edition`/`id` go into the "Source details"
// disclosure, so they're carried separately rather than folded into the compact string.
//
// ACIM locators are deliberately NOT rendered as canonical Chapter/Section/Paragraph
// citations: the numbers are positional block ordinals assigned at import (see
// docs/graph-explorer-inspection.md), so they carry an explicit "not a verified citation"
// caveat. Bible verse refs are real citations and carry none.
export const LocatorKind = {
  acim: "acim",
  verse: "verse",
  fallback: "fallback",
} as const;
export type LocatorKind = (typeof LocatorKind)[keyof typeof LocatorKind];

export type GraphLocator =
  | { kind: typeof LocatorKind.acim; compact: string; caveat: true; edition: string; id: string }
  | { kind: typeof LocatorKind.verse; compact: string; id: string }
  | { kind: typeof LocatorKind.fallback; compact: string };

export const graphSourceLocator = (p: PassageRef): GraphLocator => {
  if (p.book === "ACIM" && p.chapter) {
    const parts = ["A Course in Miracles", `Ch ${p.chapter}`];
    if (p.section === 0) parts.push("Introduction");
    else if (p.section != null) parts.push(`Sec ${p.section}`);
    if (p.paragraph != null) parts.push(`Block ${p.paragraph}`);
    return {
      kind: LocatorKind.acim,
      compact: parts.join(" · "),
      caveat: true,
      edition: p.edition,
      id: p.source_id,
    };
  }

  if (p.book && p.verse != null) {
    return {
      kind: LocatorKind.verse,
      compact: `${p.book} ${p.chapter}:${p.verse}`,
      id: p.source_id,
    };
  }

  return { kind: LocatorKind.fallback, compact: p.source_id };
};
