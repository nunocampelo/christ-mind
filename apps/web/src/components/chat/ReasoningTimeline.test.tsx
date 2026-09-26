import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ReasoningTimeline from "@/components/chat/ReasoningTimeline";

describe("ReasoningTimeline", () => {
  it("renders nothing when there are no steps", () => {
    const { container } = render(<ReasoningTimeline steps={[]} busy={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders each step label", () => {
    render(
      <ReasoningTimeline
        steps={[
          "Mapped situation to 2 concept(s)",
          "Calling find_claims",
          "find_claims returned",
        ]}
        busy={false}
      />,
    );
    const steps = screen.getAllByTestId("reasoning-step");
    expect(steps.map((s) => s.textContent)).toEqual([
      "Mapped situation to 2 concept(s)",
      "Calling find_claims",
      "find_claims returned",
    ]);
  });

  it("summarizes the step count and the last-called tool", () => {
    render(
      <ReasoningTimeline
        steps={["Calling find_claims", "find_claims returned", "Calling chain_claims"]}
        busy={false}
      />,
    );
    expect(screen.getByText("3 steps")).toBeInTheDocument();
    expect(screen.getByText("chain_claims")).toBeInTheDocument();
  });

  it("shows the argument in the step list but only the tool name in the chip", () => {
    render(
      <ReasoningTimeline
        steps={[
          'Calling find_claims_for_entity for "the ego"',
          "find_claims_for_entity returned 8 claim(s)",
        ]}
        busy={false}
      />,
    );
    const steps = screen.getAllByTestId("reasoning-step");
    expect(steps.map((s) => s.textContent)).toEqual([
      'Calling find_claims_for_entity for "the ego"',
      "find_claims_for_entity returned 8 claim(s)",
    ]);
    // The collapsed chip shows the bare tool name, not the argument.
    expect(screen.getByText("find_claims_for_entity")).toBeInTheDocument();
  });

  it("singularizes the count for one step", () => {
    render(<ReasoningTimeline steps={["Calling find_claims"]} busy={false} />);
    expect(screen.getByText("1 step")).toBeInTheDocument();
  });

  it("is open while busy and collapses once settled", () => {
    const { rerender } = render(
      <ReasoningTimeline steps={["Calling find_claims"]} busy={true} />,
    );
    const panel = screen.getByTestId("reasoning-timeline") as HTMLDetailsElement;
    expect(panel.open).toBe(true);

    rerender(<ReasoningTimeline steps={["Calling find_claims"]} busy={false} />);
    expect(panel.open).toBe(false);
  });
});
