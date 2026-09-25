import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentAnswer } from "@/api/agentApi";
import CitedAnswer from "@/components/chat/CitedAnswer";

const CLAIM = {
  claim_id: "c1",
  source_id: "T-1.II.3",
  subject: "the ego",
  predicate: "teaches",
  object: "attack",
  verb_phrase: "teaches",
  polarity: "affirmed",
  evidence: "The ego teaches attack.",
};

const ANSWER: AgentAnswer = {
  text: "Forgiveness undoes it.",
  concepts: ["forgiveness"],
  cited_claims: [CLAIM],
  inferred_chains: [{ inferred: true, links: [CLAIM] }],
};

describe("CitedAnswer", () => {
  it("renders cited claims and inferred chains in distinct regions", () => {
    render(<CitedAnswer answer={ANSWER} streamedText="Forgiveness undoes it." />);

    const cited = screen.getByTestId("cited-claims");
    const inferred = screen.getByTestId("inferred-chains");
    expect(cited).toBeInTheDocument();
    expect(inferred).toBeInTheDocument();

    // The cited region shows the source id and the evidence quote.
    expect(within(cited).getByText("T-1.II.3")).toBeInTheDocument();
    expect(within(cited).getByText("The ego teaches attack.")).toBeInTheDocument();

    // The inferred region is explicitly marked and its links stay source-attributed.
    expect(within(inferred).getByText("Inferred")).toBeInTheDocument();
    expect(within(inferred).getByTestId("inferred-chain")).toBeInTheDocument();
    expect(within(inferred).getByText("T-1.II.3")).toBeInTheDocument();
  });

  it("renders only the cited section when there are no inferred chains", () => {
    render(
      <CitedAnswer
        answer={{ ...ANSWER, inferred_chains: [] }}
        streamedText=""
      />,
    );
    expect(screen.getByTestId("cited-claims")).toBeInTheDocument();
    expect(screen.queryByTestId("inferred-chains")).not.toBeInTheDocument();
  });

  it("prefixes a negated claim's gloss so it can't read as an affirmation", () => {
    render(
      <CitedAnswer
        answer={{
          ...ANSWER,
          inferred_chains: [],
          cited_claims: [
            {
              ...CLAIM,
              subject: "God",
              verb_phrase: "is",
              object: "partial",
              polarity: "negated",
              evidence: "God is NOT partial.",
            },
          ],
        }}
        streamedText=""
      />,
    );
    const cited = screen.getByTestId("cited-claims");
    expect(within(cited).getByText("Not: God is partial")).toBeInTheDocument();
    expect(within(cited).getByText("God is NOT partial.")).toBeInTheDocument();
  });

  it("does not render the string 'null' for a claim with a null object", () => {
    render(
      <CitedAnswer
        answer={{
          ...ANSWER,
          inferred_chains: [],
          cited_claims: [{ ...CLAIM, object: null }],
        }}
        streamedText=""
      />,
    );
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });
});
