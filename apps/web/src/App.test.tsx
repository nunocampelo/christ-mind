import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { AgentAnswer, AgentStreamEvent } from "@/api/agentApi";
import App from "@/App";

const ANSWER: AgentAnswer = {
  text: "Forgiveness undoes it.",
  concepts: ["forgiveness"],
  cited_claims: [
    {
      claim_id: "c1",
      source_id: "s1",
      subject: "the ego",
      predicate: "teaches",
      object: "attack",
      verb_phrase: "teaches",
      polarity: "affirmed",
      evidence: "The ego teaches attack.",
    },
  ],
  inferred_chains: [],
};

const streamOf =
  (events: AgentStreamEvent[]) =>
  async function* () {
    for (const event of events) yield event;
  };

describe("PR 2 — ask and get a cited answer", () => {
  it("shows the landing screen before any turn", () => {
    render(<App streamFn={streamOf([])} />);
    expect(
      screen.getByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
  });

  it("keeps send disabled until the composer has text", async () => {
    const user = userEvent.setup();
    render(<App streamFn={streamOf([])} />);
    expect(screen.getByTestId("composer-send")).toBeDisabled();
    await user.type(screen.getByTestId("composer-input"), "hi");
    expect(screen.getByTestId("composer-send")).toBeEnabled();
  });

  it("posts the message and renders the markdown reply", async () => {
    const user = userEvent.setup();
    render(
      <App
        streamFn={streamOf([
          { kind: "text", delta: "Forgiveness undoes it." },
          { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
        ])}
      />,
    );

    await user.type(screen.getByTestId("composer-input"), "I can't forgive");
    await user.click(screen.getByTestId("composer-send"));

    expect(screen.getByTestId("user-turn")).toHaveTextContent("I can't forgive");
    expect(screen.getByTestId("agent-turn")).toHaveTextContent(
      "Forgiveness undoes it.",
    );
  });

  it("renders the cited answer, keeping cited distinct from inferred", async () => {
    const user = userEvent.setup();
    render(
      <App
        streamFn={streamOf([
          { kind: "text", delta: "Forgiveness undoes it." },
          {
            kind: "answer",
            answer: { ...ANSWER, inferred_chains: [{ inferred: true, links: ANSWER.cited_claims }] },
          },
          { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
        ])}
      />,
    );

    await user.type(screen.getByTestId("composer-input"), "help");
    await user.click(screen.getByTestId("composer-send"));

    expect(screen.getByTestId("cited-claims")).toHaveTextContent("s1");
    expect(screen.getByTestId("inferred-chains")).toHaveTextContent("Inferred");
  });

  it("submits on Enter but not Shift+Enter", async () => {
    const user = userEvent.setup();
    render(
      <App
        streamFn={streamOf([
          { kind: "text", delta: "ok" },
          { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
        ])}
      />,
    );
    const input = screen.getByTestId("composer-input");

    await user.type(input, "hi{Shift>}{Enter}{/Shift}");
    expect(screen.queryByTestId("user-turn")).not.toBeInTheDocument();

    await user.type(input, "{Enter}");
    expect(screen.getByTestId("user-turn")).toBeInTheDocument();
  });

  it("shows an error strip when the stream errors", async () => {
    const user = userEvent.setup();
    render(<App streamFn={streamOf([{ kind: "error", message: "boom" }])} />);

    await user.type(screen.getByTestId("composer-input"), "help");
    await user.click(screen.getByTestId("composer-send"));

    expect(screen.getByTestId("error-strip")).toHaveTextContent("boom");
  });

  it("removes the empty agent bubble when nothing is returned", async () => {
    const user = userEvent.setup();
    render(
      <App
        streamFn={streamOf([{ kind: "status", state: "TASK_STATE_COMPLETED", text: "" }])}
      />,
    );

    await user.type(screen.getByTestId("composer-input"), "help");
    await user.click(screen.getByTestId("composer-send"));

    expect(screen.getByTestId("user-turn")).toBeInTheDocument();
    expect(screen.queryByTestId("agent-turn")).not.toBeInTheDocument();
  });
});
