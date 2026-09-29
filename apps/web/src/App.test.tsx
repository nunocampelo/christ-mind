import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ComponentProps } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { AgentAnswer, AgentStreamEvent } from "@/api/agentApi";
import App from "@/App";

// App reads the route param, so every render goes through the router with both routes
// mounted. `at` sets the starting URL (default "/" = a fresh chat).
const renderApp = (props: ComponentProps<typeof App> = {}, at = "/") =>
  render(
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route path="/" element={<App {...props} />} />
        <Route path="/c/:conversationId" element={<App {...props} />} />
      </Routes>
    </MemoryRouter>,
  );

const ANSWER: AgentAnswer = {
  text: "Forgiveness undoes it.",
  concepts: ["forgiveness"],
  cited_claims: [
    {
      claim_id: "c1",
      source_id: "s1",
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
      evidence_context: "",
      evidence_start: 0,
      evidence_end: 0,
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
    renderApp({ streamFn: streamOf([]) });
    expect(
      screen.getByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
  });

  it("keeps send disabled until the composer has text", async () => {
    const user = userEvent.setup();
    renderApp({ streamFn: streamOf([]) });
    expect(screen.getByTestId("composer-send")).toBeDisabled();
    await user.type(screen.getByTestId("composer-input"), "hi");
    expect(screen.getByTestId("composer-send")).toBeEnabled();
  });

  it("posts the message and renders the markdown reply", async () => {
    const user = userEvent.setup();
    renderApp({
      streamFn: streamOf([
        { kind: "text", delta: "Forgiveness undoes it." },
        { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
      ]),
    });

    await user.type(screen.getByTestId("composer-input"), "I can't forgive");
    await user.click(screen.getByTestId("composer-send"));

    expect(screen.getByTestId("user-turn")).toHaveTextContent("I can't forgive");
    expect(screen.getByTestId("agent-turn")).toHaveTextContent(
      "Forgiveness undoes it.",
    );
  });

  it("renders the cited answer, keeping cited distinct from inferred", async () => {
    const user = userEvent.setup();
    renderApp({
      streamFn: streamOf([
        { kind: "text", delta: "Forgiveness undoes it." },
        {
          kind: "answer",
          answer: { ...ANSWER, inferred_chains: [{ inferred: true, links: ANSWER.cited_claims }] },
        },
        { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
      ]),
    });

    await user.type(screen.getByTestId("composer-input"), "help");
    await user.click(screen.getByTestId("composer-send"));

    expect(screen.getByTestId("cited-claims")).toHaveTextContent("s1");
    expect(screen.getByTestId("inferred-chains")).toHaveTextContent("Inferred");
  });

  it("submits on Enter but not Shift+Enter", async () => {
    const user = userEvent.setup();
    renderApp({
      streamFn: streamOf([
        { kind: "text", delta: "ok" },
        { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
      ]),
    });
    const input = screen.getByTestId("composer-input");

    await user.type(input, "hi{Shift>}{Enter}{/Shift}");
    expect(screen.queryByTestId("user-turn")).not.toBeInTheDocument();

    await user.type(input, "{Enter}");
    expect(screen.getByTestId("user-turn")).toBeInTheDocument();
  });

  it("shows an error strip when the stream errors", async () => {
    const user = userEvent.setup();
    renderApp({ streamFn: streamOf([{ kind: "error", message: "boom" }]) });

    await user.type(screen.getByTestId("composer-input"), "help");
    await user.click(screen.getByTestId("composer-send"));

    expect(screen.getByTestId("error-strip")).toHaveTextContent("boom");
  });

  it("removes the empty agent bubble when nothing is returned", async () => {
    const user = userEvent.setup();
    renderApp({
      streamFn: streamOf([{ kind: "status", state: "TASK_STATE_COMPLETED", text: "" }]),
    });

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

    renderApp({ streamFn });

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

    renderApp({ streamFn });

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

    renderApp({ streamFn, recoverFn });

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

describe("PR D — sidebar, routing, and rehydration by URL", () => {
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

  const summaries = [
    {
      conversation_id: "ctx-restored",
      summary: "earlier thread",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-02T00:00:00",
    },
    {
      conversation_id: "ctx-other",
      summary: "another thread",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
    },
  ];

  it("lists conversations in the sidebar, highlighting the active one", async () => {
    renderApp(
      {
        streamFn: streamOf([]),
        loadConversation: async () => detail,
        listConversations: async () => summaries,
      },
      "/c/ctx-restored",
    );

    const items = await screen.findAllByTestId("conversation-item");
    expect(items.map((i) => i.textContent)).toEqual([
      "earlier thread",
      "another thread",
    ]);
    const active = items.find((i) => i.getAttribute("data-active") === "true");
    expect(active).toHaveTextContent("earlier thread");
  });

  it("rehydrates the transcript for the conversation in the URL", async () => {
    renderApp(
      {
        streamFn: streamOf([]),
        loadConversation: async () => detail,
        listConversations: async () => summaries,
      },
      "/c/ctx-restored",
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

  it("jumps to the bottom when landing on a rehydrated conversation", async () => {
    // jsdom doesn't lay out, so pin the scroller taller than its viewport and capture writes
    // to scrollTop — the mount effect should snap it to scrollHeight (the newest turn).
    let scrollTop = 0;
    const proto = window.HTMLElement.prototype;
    const origScrollTop = Object.getOwnPropertyDescriptor(proto, "scrollTop");
    const origScrollHeight = Object.getOwnPropertyDescriptor(proto, "scrollHeight");
    const setSpy = vi.fn((v: number) => {
      scrollTop = v;
    });
    Object.defineProperty(proto, "scrollTop", {
      configurable: true,
      get: () => scrollTop,
      set: setSpy,
    });
    Object.defineProperty(proto, "scrollHeight", { configurable: true, value: 2000 });
    try {
      renderApp(
        {
          streamFn: streamOf([]),
          loadConversation: async () => detail,
          listConversations: async () => summaries,
        },
        "/c/ctx-restored",
      );

      await screen.findByTestId("agent-turn");
      await waitFor(() => expect(setSpy).toHaveBeenCalledWith(2000));
    } finally {
      if (origScrollTop) Object.defineProperty(proto, "scrollTop", origScrollTop);
      if (origScrollHeight) Object.defineProperty(proto, "scrollHeight", origScrollHeight);
    }
  });

  it("shows the landing at the root route (new chat)", async () => {
    renderApp(
      {
        streamFn: streamOf([]),
        listConversations: async () => summaries,
      },
      "/",
    );

    expect(
      await screen.findByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("user-turn")).not.toBeInTheDocument();
  });

  it("falls back to the landing when the URL's conversation is unknown (404)", async () => {
    renderApp(
      {
        streamFn: streamOf([]),
        loadConversation: async () => null,
        listConversations: async () => summaries,
      },
      "/c/ctx-stale",
    );

    expect(
      await screen.findByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
  });

  it("shows the landing (no stale transcript) after New chat from a conversation", async () => {
    const user = userEvent.setup();
    renderApp(
      {
        streamFn: streamOf([]),
        loadConversation: async () => detail,
        listConversations: async () => summaries,
      },
      "/c/ctx-restored",
    );
    // Start on the conversation.
    expect(await screen.findByTestId("user-turn")).toHaveTextContent(
      "an earlier question",
    );

    await user.click(screen.getByTestId("new-chat"));

    // The keyed chat must reseed empty, not carry the previous conversation's turns.
    expect(
      await screen.findByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("user-turn")).not.toBeInTheDocument();
  });

  it("keeps the streamed answer when a fresh chat self-assigns its id mid-stream", async () => {
    const user = userEvent.setup();
    // The server mints the contextId on the first frame, so the stream emits it before the
    // answer. If the refetch races the still-in-progress run, history has only the user
    // message (the agent turn isn't persisted until the stream ends) — this loader models
    // that race. The answer must survive it.
    const loadConversation = vi.fn(async () => ({
      conversation_id: "ctx-fresh",
      summary: "I can't forgive",
      created_at: "2026-01-01T00:00:00",
      updated_at: "2026-01-01T00:00:00",
      messages: [
        {
          conversation_id: "ctx-fresh",
          role: "user",
          content: "I can't forgive",
          message_json: null,
          timestamp: "2026-01-01T00:00:00",
          sequence: 1,
        },
      ],
    }));
    renderApp(
      {
        streamFn: streamOf([
          { kind: "contextId", contextId: "ctx-fresh" },
          { kind: "text", delta: "Forgiveness undoes it." },
          { kind: "answer", answer: ANSWER },
          { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
        ]),
        loadConversation,
        listConversations: async () => summaries,
      },
      "/",
    );

    await user.type(screen.getByTestId("composer-input"), "I can't forgive");
    await user.click(screen.getByTestId("composer-send"));

    // The bubble that streamed in place is not torn down by the self-navigation.
    expect(await screen.findByTestId("agent-turn")).toHaveTextContent(
      "Forgiveness undoes it.",
    );
    expect(screen.getByTestId("cited-claims")).toHaveTextContent("s1");
    // The live chat must not refetch its own in-flight conversation (that's the race).
    expect(loadConversation).not.toHaveBeenCalled();
  });

  it("renames a conversation through the sidebar and refreshes the list", async () => {
    const user = userEvent.setup();
    const renameConversation = vi.fn(async () => {});
    let listed = summaries;
    renderApp(
      {
        streamFn: streamOf([]),
        loadConversation: async () => detail,
        listConversations: async () => listed,
        renameConversation,
      },
      "/c/ctx-restored",
    );
    await screen.findAllByTestId("conversation-item");

    await user.click(screen.getAllByTestId("rename-conversation")[0]);
    const input = screen.getByTestId("rename-input");
    await user.clear(input);
    // Once renamed, a refetch returns the new title.
    listed = [{ ...summaries[0], summary: "Renamed thread" }, summaries[1]];
    await user.type(input, "Renamed thread{Enter}");

    expect(renameConversation).toHaveBeenCalledWith("ctx-restored", "Renamed thread");
    expect(await screen.findByText("Renamed thread")).toBeInTheDocument();
  });

  it("deleting the active conversation navigates to the landing", async () => {
    const user = userEvent.setup();
    const deleteConversation = vi.fn(async () => {});
    let listed = summaries;
    renderApp(
      {
        streamFn: streamOf([]),
        loadConversation: async () => detail,
        listConversations: async () => listed,
        deleteConversation,
      },
      "/c/ctx-restored",
    );
    expect(await screen.findByTestId("user-turn")).toBeInTheDocument();

    await user.click(screen.getAllByTestId("delete-conversation")[0]);
    listed = [summaries[1]]; // the active one is gone after refetch
    await user.click(screen.getByTestId("confirm-delete"));

    expect(deleteConversation).toHaveBeenCalledWith("ctx-restored");
    expect(
      await screen.findByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("user-turn")).not.toBeInTheDocument();
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
    renderApp({
      streamFn: streamOf([
        { kind: "text", delta: "a long answer" },
        { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
      ]),
    });
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
