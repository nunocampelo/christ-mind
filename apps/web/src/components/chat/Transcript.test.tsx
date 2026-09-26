import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Transcript from "@/components/chat/Transcript";
import { TurnRole, type Turn } from "@/hooks/useA2AChat";

const turn = (over: Partial<Turn> & Pick<Turn, "id" | "role">): Turn => ({
  text: "",
  steps: [],
  ...over,
});

describe("Transcript scroll anchoring (PR 7)", () => {
  it("renders the tail spacer at the given height", () => {
    render(
      <Transcript
        turns={[turn({ id: 0, role: TurnRole.user, text: "hi" })]}
        busy={false}
        spacerHeight={240}
      />,
    );
    expect(screen.getByTestId("tail-spacer")).toHaveStyle({ height: "240px" });
  });

  it("marks each turn with the data-role the scroll anchor queries", () => {
    render(
      <Transcript
        turns={[
          turn({ id: 0, role: TurnRole.user, text: "first" }),
          turn({ id: 1, role: TurnRole.agent, text: "reply" }),
        ]}
        busy={false}
      />,
    );
    expect(screen.getByTestId("user-turn")).toHaveAttribute("data-role", "user");
    expect(screen.getByTestId("agent-turn")).toHaveAttribute("data-role", "agent");
  });
});
