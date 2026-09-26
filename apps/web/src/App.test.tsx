import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
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

describe("PR 5 — stop a running answer", () => {
  it("swaps send for stop while streaming and drops a notice on stop", async () => {
    const user = userEvent.setup();
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const streamFn = () =>
      (async function* () {
        yield { kind: "text", delta: "partial" } as AgentStreamEvent;
        await gate;
      })();

    render(<App streamFn={streamFn} />);

    await user.type(screen.getByTestId("composer-input"), "help");
    await user.click(screen.getByTestId("composer-send"));

    const stop = await screen.findByTestId("composer-stop");
    expect(screen.queryByTestId("composer-send")).not.toBeInTheDocument();

    await user.click(stop);
    release();

    expect(await screen.findByTestId("notice-turn")).toHaveTextContent(
      "Request stopped",
    );
    expect(screen.getByTestId("agent-turn")).toHaveTextContent("partial");
    expect(screen.getByTestId("composer-send")).toBeInTheDocument();
    expect(screen.queryByTestId("error-strip")).not.toBeInTheDocument();
  });

  it("keeps the input typable while streaming but does not submit on Enter", async () => {
    const user = userEvent.setup();
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const streamFn = () =>
      (async function* () {
        yield { kind: "text", delta: "…" } as AgentStreamEvent;
        await gate;
      })();

    render(<App streamFn={streamFn} />);

    const input = screen.getByTestId("composer-input");
    await user.type(input, "first");
    await user.click(screen.getByTestId("composer-send"));
    await screen.findByTestId("composer-stop");

    // The field is still enabled and accepts a draft mid-stream (send cleared it first).
    expect(input).toBeEnabled();
    await user.type(input, "next question{Enter}");
    expect(input).toHaveValue("next question");
    // Enter did not start a second turn (still exactly one user turn).
    expect(screen.getAllByTestId("user-turn")).toHaveLength(1);

    await act(async () => {
      release();
    });
  });
});

describe("PR 6 — reconnect a dropped answer", () => {
  it("shows a reconnect chip on the tail notice and refills the bubble", async () => {
    const user = userEvent.setup();
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const streamFn = () =>
      (async function* () {
        yield { kind: "taskId", taskId: "task-1" } as AgentStreamEvent;
        yield { kind: "text", delta: "partial" } as AgentStreamEvent;
        await gate;
      })();
    const recoverFn = () =>
      (async function* () {
        yield { kind: "text", delta: " and the rest." } as AgentStreamEvent;
        yield {
          kind: "status",
          state: "TASK_STATE_COMPLETED",
          text: "",
        } as AgentStreamEvent;
      })();

    render(<App streamFn={streamFn} recoverFn={recoverFn} />);

    await user.type(screen.getByTestId("composer-input"), "help");
    await user.click(screen.getByTestId("composer-send"));
    await user.click(await screen.findByTestId("composer-stop"));
    release();

    const chip = await screen.findByTestId("reconnect-chip");
    await user.click(chip);

    await waitFor(() =>
      expect(screen.getByTestId("agent-turn")).toHaveTextContent(
        "partial and the rest.",
      ),
    );
    expect(screen.queryByTestId("notice-turn")).not.toBeInTheDocument();
  });
});

describe("PR C — rehydrate the stored conversation on load", () => {
  const CONTEXT_KEY = "christ-mind.agent.contextId";

  const detail = {
    conversation_id: "ctx-restored",
    summary: "earlier thread",
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    messages: [
      {
        conversation_id: "ctx-restored",
        role: "user",
        content: "an earlier question",
        message_json: null,
        timestamp: "2026-01-01T00:00:00",
        sequence: 1,
      },
      {
        conversation_id: "ctx-restored",
        role: "agent",
        // content mirrors AgentAnswer.text (what the executor persists); the turn renders
        // the structured answer's prose + citations.
        content: ANSWER.text,
        message_json: ANSWER,
        timestamp: "2026-01-01T00:00:00",
        sequence: 2,
      },
    ],
  };

  afterEach(() => sessionStorage.clear());

  it("restores the transcript from the stored conversation", async () => {
    sessionStorage.setItem(CONTEXT_KEY, "ctx-restored");
    render(
      <App streamFn={streamOf([])} loadConversation={async () => detail} />,
    );

    expect(await screen.findByTestId("agent-turn")).toHaveTextContent(
      "Forgiveness undoes it.",
    );
    expect(screen.getByTestId("user-turn")).toHaveTextContent(
      "an earlier question",
    );
    // The structured answer rehydrated too (citations render, not just prose).
    expect(screen.getByTestId("cited-claims")).toHaveTextContent("s1");
  });

  it("starts fresh (landing) when the stored id is unknown (404)", async () => {
    sessionStorage.setItem(CONTEXT_KEY, "ctx-stale");
    render(
      <App streamFn={streamOf([])} loadConversation={async () => null} />,
    );

    expect(
      await screen.findByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
    expect(sessionStorage.getItem(CONTEXT_KEY)).toBeNull();
  });
});

describe("PR 7 — jump-to-bottom button", () => {
  const stubGeometry = (
    el: HTMLElement,
    geo: { scrollTop: number; scrollHeight: number; clientHeight: number },
  ) => {
    Object.defineProperty(el, "scrollTop", { configurable: true, value: geo.scrollTop });
    Object.defineProperty(el, "scrollHeight", {
      configurable: true,
      value: geo.scrollHeight,
    });
    Object.defineProperty(el, "clientHeight", {
      configurable: true,
      value: geo.clientHeight,
    });
  };

  it("reveals the button when the transcript is scrolled up, hides it at the bottom", async () => {
    const user = userEvent.setup();
    render(
      <App
        streamFn={streamOf([
          { kind: "text", delta: "a long answer" },
          { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
        ])}
      />,
    );
    await user.type(screen.getByTestId("composer-input"), "hi");
    await user.click(screen.getByTestId("composer-send"));

    const scroller = screen.getByRole("main");
    const button = screen.getByTestId("scroll-to-bottom");

    // Scrolled well above the bottom → button becomes interactive.
    stubGeometry(scroller, { scrollTop: 0, scrollHeight: 2000, clientHeight: 800 });
    act(() => scroller.dispatchEvent(new Event("scroll")));
    await waitFor(() => expect(button).not.toHaveClass("pointer-events-none"));
    expect(button).toHaveClass("opacity-100");

    // Back at the bottom → button hides.
    stubGeometry(scroller, { scrollTop: 1200, scrollHeight: 2000, clientHeight: 800 });
    act(() => scroller.dispatchEvent(new Event("scroll")));
    await waitFor(() => expect(button).toHaveClass("pointer-events-none"));
  });
});
