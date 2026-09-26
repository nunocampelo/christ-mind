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

    // The evidence sits in a collapsible "Sources" panel, collapsed by default.
    expect(cited.tagName).toBe("DETAILS");
    expect(cited).not.toHaveAttribute("open");
    expect(within(cited).getByText("Sources")).toBeInTheDocument();

    // The cited region shows the source id and the evidence quote.
    expect(within(cited).getByText("T-1.II.3")).toBeInTheDocument();
    expect(within(cited).getByText("The ego teaches attack.")).toBeInTheDocument();

    // The inferred region is explicitly marked and its links stay source-attributed.
    expect(within(inferred).getByText("Inferred")).toBeInTheDocument();
    expect(within(inferred).getByTestId("inferred-chain")).toBeInTheDocument();
    expect(within(inferred).getByText("T-1.II.3")).toBeInTheDocument();
  });

  it("renders an inline superscript for a cited statement, not the literal marker", () => {
    render(
      <CitedAnswer
        answer={{ ...ANSWER, text: "Forgiveness undoes it. [c1]", inferred_chains: [] }}
        streamedText=""
      />,
    );
    // The marker becomes a reference link to the source anchor; the literal "[c1]"
    // never appears in the prose.
    const marker = screen.getByRole("link", { name: "Source 1" });
    expect(marker).toHaveAttribute("href", "#src-c1");
    expect(marker).toHaveTextContent("1");
    expect(screen.queryByText(/\[c1\]/)).not.toBeInTheDocument();
  });

  it("orders the Sources panel by citation order, not retrieval order", () => {
    const first = { ...CLAIM, claim_id: "a", source_id: "SRC-A" };
    const second = { ...CLAIM, claim_id: "b", source_id: "SRC-B" };
    render(
      <CitedAnswer
        answer={{
          ...ANSWER,
          // retrieved [a, b], but the prose cites b before a -> panel should read b, a.
          text: "First point. [b] Second point. [a]",
          cited_claims: [first, second],
          inferred_chains: [],
        }}
        streamedText=""
      />,
    );
    const cited = screen.getByTestId("cited-claims");
    const sources = within(cited).getAllByText(/SRC-[AB]/);
    expect(sources.map((el) => el.textContent)).toEqual(["SRC-B", "SRC-A"]);
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
