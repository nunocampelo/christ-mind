import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AgentAnswer } from "@/api/agentApi";
import CitedAnswer from "@/components/chat/CitedAnswer";

const CLAIM = {
  claim_id: "c1",
  source_id: "T-1.II.3",
  book: "",
  chapter: 0,
  verse: null,
  section: null,
  paragraph: null,
  edition: "",
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
    expect(marker).toHaveAttribute("href", "#src-0-c1");
    expect(marker).toHaveTextContent("1");
    expect(screen.queryByText(/\[c1\]/)).not.toBeInTheDocument();
  });

  it("namespaces the source anchor by turn so same-claim markers don't collide", () => {
    // Two messages can cite the same claim_id; a bare "#src-c1" would jump to whichever
    // rendered first. The turnId keeps each message's marker pointing at its own source.
    const answer = {
      ...ANSWER,
      text: "Forgiveness undoes it. [c1]",
      inferred_chains: [],
    };
    const { rerender } = render(<CitedAnswer answer={answer} streamedText="" turnId={3} />);
    expect(screen.getByRole("link", { name: "Source 1" })).toHaveAttribute(
      "href",
      "#src-3-c1",
    );
    expect(screen.getByTestId("cited-claim")).toHaveAttribute("id", "src-3-c1");

    rerender(<CitedAnswer answer={answer} streamedText="" turnId={7} />);
    expect(screen.getByRole("link", { name: "Source 1" })).toHaveAttribute(
      "href",
      "#src-7-c1",
    );
    expect(screen.getByTestId("cited-claim")).toHaveAttribute("id", "src-7-c1");
  });

  it("renders superscripts while streaming, before the evidence artifact lands", () => {
    // The answer's structured payload hasn't arrived (empty text/claims); the prose is
    // still streaming with raw markers. Superscripts must show now, numbered, with no
    // literal "[c1]" leaking through and no source link yet (nothing to jump to).
    render(
      <CitedAnswer
        answer={{ text: "", concepts: [], cited_claims: [], inferred_chains: [] }}
        streamedText="Forgiveness undoes it. [c1] It heals. [c2]"
      />,
    );
    expect(screen.queryByText(/\[c1\]/)).not.toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
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

  it("renders a readable ACIM reference with a roman-numeral section", () => {
    render(
      <CitedAnswer
        answer={{
          ...ANSWER,
          inferred_chains: [],
          cited_claims: [
            { ...CLAIM, book: "ACIM", chapter: 3, section: 4, paragraph: 25 },
          ],
        }}
        streamedText=""
      />,
    );
    expect(screen.getByText("A Course in Miracles")).toBeInTheDocument();
    expect(screen.getByText("Chapter 3 Section IV Paragraph 25")).toBeInTheDocument();
  });

  it("renders section 0 as the chapter Introduction", () => {
    render(
      <CitedAnswer
        answer={{
          ...ANSWER,
          inferred_chains: [],
          cited_claims: [
            { ...CLAIM, book: "ACIM", chapter: 1, section: 0, paragraph: 1 },
          ],
        }}
        streamedText=""
      />,
    );
    expect(screen.getByText("A Course in Miracles")).toBeInTheDocument();
    expect(screen.getByText("Chapter 1 Introduction Paragraph 1")).toBeInTheDocument();
  });

  it("renders a Bible reference as book chapter:verse", () => {
    render(
      <CitedAnswer
        answer={{
          ...ANSWER,
          inferred_chains: [],
          cited_claims: [{ ...CLAIM, book: "Matthew", chapter: 5, verse: 7 }],
        }}
        streamedText=""
      />,
    );
    expect(screen.getByText("Matthew")).toBeInTheDocument();
    expect(screen.getByText("5:7")).toBeInTheDocument();
  });

  it("keeps an uncited claim's quote below its gloss", () => {
    // No inline [c1] marker in the prose -> the claim has no ordinal. The gloss, quote and
    // source must still stack inside one body cell rather than the quote floating right.
    render(
      <CitedAnswer answer={{ ...ANSWER, inferred_chains: [] }} streamedText="" />,
    );
    const entry = screen.getByTestId("cited-claim");
    const body = entry.querySelector(".cited-claim-body");
    expect(body).not.toBeNull();
    expect(within(body as HTMLElement).getByText("The ego teaches attack.")).toBeInTheDocument();
    expect(within(body as HTMLElement).getByText("the ego teaches attack")).toBeInTheDocument();
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
