import type { Attribution, Mode, Polarity } from "@/api/graphArtifact";

// The single source of truth for how a claim's qualifiers read, so the relationship list's
// inline suffix and the evidence panel's chips can never drift apart. Default `assertion`
// mode and `course` attribution carry no label (they're the unmarked case); `Negated` is
// always explicit. Order: polarity, mode, attribution.
export const qualifierLabels = (
  polarity: Polarity,
  mode: Mode,
  attribution: Attribution,
): string[] => {
  const labels: string[] = [];
  if (polarity === "negated") labels.push("Negated");
  if (mode !== "assertion") labels.push(mode.charAt(0).toUpperCase() + mode.slice(1));
  if (attribution !== "course") labels.push(`Attributed to ${attribution}`);
  return labels;
};
