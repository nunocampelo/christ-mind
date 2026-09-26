import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AgentAnswer, AgentStreamEvent } from "@/api/agentApi";
import useA2AChat, { TurnRole } from "@/hooks/useA2AChat";

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

describe("useA2AChat", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("appends a user turn and streams prose into the agent turn", async () => {
    const streamFn = streamOf([
      { kind: "text", delta: "Forgiveness " },
      { kind: "text", delta: "undoes it." },
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("I can't forgive");
    });

    expect(result.current.turns).toHaveLength(2);
    expect(result.current.turns[0]).toMatchObject({
      role: TurnRole.user,
      text: "I can't forgive",
    });
    expect(result.current.turns[1]).toMatchObject({
      role: TurnRole.agent,
      text: "Forgiveness undoes it.",
    });
  });

  it("sets the structured answer on the agent turn", async () => {
    const streamFn = streamOf([
      { kind: "text", delta: "Forgiveness undoes it." },
      { kind: "answer", answer: ANSWER },
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(result.current.turns[1].answer).toEqual(ANSWER);
  });

  it("keeps an answer-only turn even when no prose streamed", async () => {
    const streamFn = streamOf([
      { kind: "answer", answer: ANSWER },
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(result.current.turns).toHaveLength(2);
    expect(result.current.turns[1].text).toBe("");
    expect(result.current.turns[1].answer).toEqual(ANSWER);
  });

  it("accumulates status step labels on the agent turn", async () => {
    const streamFn = streamOf([
      { kind: "status", state: "TASK_STATE_WORKING", text: "Mapped situation to 2 concept(s)" },
      { kind: "status", state: "TASK_STATE_WORKING", text: "Calling find_claims" },
      { kind: "status", state: "TASK_STATE_WORKING", text: "find_claims returned" },
      { kind: "text", delta: "Forgiveness undoes it." },
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(result.current.turns[1].steps).toEqual([
      "Mapped situation to 2 concept(s)",
      "Calling find_claims",
      "find_claims returned",
    ]);
  });

  it("does not render the terminal completion message as a reasoning step", async () => {
    // The a2a `complete` re-carries the full answer prose for non-streaming clients. The
    // streaming client already has it as prose; appending it as a step would duplicate the
    // whole answer in the trace.
    const streamFn = streamOf([
      { kind: "status", state: "TASK_STATE_WORKING", text: "Calling find_claims" },
      { kind: "text", delta: "Forgiveness undoes it." },
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "Forgiveness undoes it." },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(result.current.turns[1].steps).toEqual(["Calling find_claims"]);
    expect(result.current.turns[1].text).toBe("Forgiveness undoes it.");
  });

  it("keeps a turn that only ran tools even with no prose or answer", async () => {
    const streamFn = streamOf([
      { kind: "status", state: "TASK_STATE_WORKING", text: "Calling find_claims" },
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(result.current.turns).toHaveLength(2);
    expect(result.current.turns[1].steps).toEqual(["Calling find_claims"]);
  });

  it("removes the agent turn when the stream returns nothing", async () => {
    const streamFn = streamOf([
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(result.current.turns).toHaveLength(1);
    expect(result.current.turns[0].role).toBe(TurnRole.user);
  });

  it("surfaces an error event", async () => {
    const streamFn = streamOf([{ kind: "error", message: "boom" }]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    await waitFor(() => expect(result.current.error).toBe("boom"));
  });

  it("ignores a second send while one is in flight", async () => {
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const streamFn = async function* () {
      await gate;
      yield { kind: "text", delta: "x" } as AgentStreamEvent;
    };
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    let first: Promise<void>;
    act(() => {
      first = result.current.send("one");
      void result.current.send("two");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));
    // Only the first send's user + agent turn exist while busy.
    expect(result.current.turns).toHaveLength(2);

    await act(async () => {
      release();
      await first;
    });
  });

  it("persists a streamed context id to sessionStorage", async () => {
    const streamFn = streamOf([
      { kind: "contextId", contextId: "ctx-1" },
      { kind: "text", delta: "hi" },
      { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(sessionStorage.getItem("christ-mind.agent.contextId")).toBe("ctx-1");
  });

  it("echoes the stored context id on the next turn", async () => {
    const streamFn = vi.fn(
      (_message: string, _contextId: string, _signal?: AbortSignal) =>
        streamOf([
          { kind: "contextId", contextId: "ctx-1" },
          { kind: "text", delta: "hi" },
          { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
        ])(),
    );
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("first");
    });
    await act(async () => {
      await result.current.send("second");
    });

    expect(streamFn.mock.calls[0].slice(0, 2)).toEqual(["first", ""]);
    expect(streamFn.mock.calls[1].slice(0, 2)).toEqual(["second", "ctx-1"]);
  });

  it("rehydrates the context id from sessionStorage on mount", async () => {
    sessionStorage.setItem("christ-mind.agent.contextId", "ctx-restored");
    const streamFn = vi.fn(
      (_message: string, _contextId: string, _signal?: AbortSignal) =>
        streamOf([
          { kind: "text", delta: "hi" },
          { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
        ])(),
    );
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("first");
    });

    expect(streamFn.mock.calls[0].slice(0, 2)).toEqual(["first", "ctx-restored"]);
  });

  it("aborts the stream, keeps the partial answer, and drops a notice", async () => {
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    let signal: AbortSignal | undefined;
    const streamFn = (_m: string, _c: string, s?: AbortSignal) =>
      (async function* () {
        signal = s;
        yield { kind: "text", delta: "partial" } as AgentStreamEvent;
        await gate;
      })();
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    let sending: Promise<void>;
    act(() => {
      sending = result.current.send("help");
    });
    await waitFor(() => expect(result.current.turns[1]?.text).toBe("partial"));

    act(() => {
      result.current.handleCancel();
    });
    expect(signal?.aborted).toBe(true);

    await act(async () => {
      release();
      await sending;
    });

    const notice = result.current.turns.find((t) => t.role === TurnRole.notice);
    expect(notice?.text).toBe("Request stopped");
    expect(result.current.turns[1].text).toBe("partial");
    expect(result.current.error).toBeNull();
    expect(result.current.busy).toBe(false);
  });

  it("drops the empty agent bubble when stopped before the first token", async () => {
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const streamFn = () =>
      (async function* () {
        await gate;
      })();
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    let sending: Promise<void>;
    act(() => {
      sending = result.current.send("help");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));

    act(() => {
      result.current.handleCancel();
    });
    await act(async () => {
      release();
      await sending;
    });

    expect(result.current.turns.some((t) => t.role === TurnRole.agent)).toBe(
      false,
    );
    expect(result.current.turns.some((t) => t.role === TurnRole.notice)).toBe(
      true,
    );
  });

  const stopAfterPartial = () => {
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
    return { streamFn, release: () => release() };
  };

  it("reconnects: refills the same bubble and removes the tail notice", async () => {
    const { streamFn, release } = stopAfterPartial();
    const recoverFn = vi.fn((_taskId: string, _textSoFar: string) =>
      streamOf([
        { kind: "text", delta: " and the rest." },
        { kind: "answer", answer: ANSWER },
        { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
      ])(),
    );
    const { result } = renderHook(() => useA2AChat({ streamFn, recoverFn }));

    let sending: Promise<void>;
    act(() => {
      sending = result.current.send("help");
    });
    await waitFor(() => expect(result.current.turns[1]?.text).toBe("partial"));
    act(() => {
      result.current.handleCancel();
    });
    await act(async () => {
      release();
      await sending;
    });

    expect(result.current.canReconnect).toBe(true);

    await act(async () => {
      await result.current.handleReconnect();
    });

    expect(recoverFn).toHaveBeenCalledWith("task-1", "partial");
    const agent = result.current.turns.find((t) => t.role === TurnRole.agent);
    expect(agent?.text).toBe("partial and the rest.");
    expect(agent?.answer).toEqual(ANSWER);
    expect(result.current.turns.some((t) => t.role === TurnRole.notice)).toBe(
      false,
    );
  });

  it("reconnects after stopping before the first token: recreates the dropped bubble", async () => {
    // Stopping right after send (a taskId has arrived but no prose) removes the empty agent
    // bubble. Reconnect must recreate it, or the recovered reply is written to a missing
    // turn id and never renders — the "I get the retry but it doesn't load" case.
    let release = () => {};
    const gate = new Promise<void>((r) => {
      release = r;
    });
    const streamFn = () =>
      (async function* () {
        yield { kind: "taskId", taskId: "task-1" } as AgentStreamEvent;
        await gate;
      })();
    const recoverFn = vi.fn((_taskId: string, _textSoFar: string) =>
      streamOf([
        { kind: "text", delta: "Forgiveness undoes it." },
        { kind: "answer", answer: ANSWER },
        { kind: "status", state: "TASK_STATE_COMPLETED", text: "" },
      ])(),
    );
    const { result } = renderHook(() => useA2AChat({ streamFn, recoverFn }));

    let sending: Promise<void>;
    act(() => {
      sending = result.current.send("help");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));
    act(() => {
      result.current.handleCancel();
    });
    await act(async () => {
      release();
      await sending;
    });

    // The empty agent bubble was dropped; only the user turn and the notice remain.
    expect(result.current.turns.some((t) => t.role === TurnRole.agent)).toBe(false);
    expect(result.current.canReconnect).toBe(true);

    await act(async () => {
      await result.current.handleReconnect();
    });

    // Nothing had streamed, so recovery replays the full answer into the recreated bubble.
    expect(recoverFn).toHaveBeenCalledWith("task-1", "");
    const agent = result.current.turns.find((t) => t.role === TurnRole.agent);
    expect(agent?.text).toBe("Forgiveness undoes it.");
    expect(agent?.answer).toEqual(ANSWER);
    expect(result.current.turns.some((t) => t.role === TurnRole.notice)).toBe(
      false,
    );
  });

  it("keeps the notice and surfaces an error when the reconnect fails", async () => {
    const { streamFn, release } = stopAfterPartial();
    const recoverFn = () => streamOf([{ kind: "error", message: "gone" }])();
    const { result } = renderHook(() => useA2AChat({ streamFn, recoverFn }));

    let sending: Promise<void>;
    act(() => {
      sending = result.current.send("help");
    });
    await waitFor(() => expect(result.current.turns[1]?.text).toBe("partial"));
    act(() => {
      result.current.handleCancel();
    });
    await act(async () => {
      release();
      await sending;
    });

    await act(async () => {
      await result.current.handleReconnect();
    });

    expect(result.current.error).toBe("gone");
    expect(result.current.turns.some((t) => t.role === TurnRole.notice)).toBe(
      true,
    );
  });

  it("does not reconnect before any task id is known", async () => {
    const recoverFn = vi.fn();
    const { result } = renderHook(() => useA2AChat({ recoverFn }));

    expect(result.current.canReconnect).toBe(false);
    await act(async () => {
      await result.current.handleReconnect();
    });
    expect(recoverFn).not.toHaveBeenCalled();
  });
});
