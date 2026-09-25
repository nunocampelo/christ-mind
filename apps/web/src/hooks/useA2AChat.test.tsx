import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
  it("appends a user turn and streams prose into the agent turn", async () => {
    const streamFn = streamOf([
      { kind: "text", delta: "Forgiveness " },
      { kind: "text", delta: "undoes it." },
      { kind: "status", state: "TASK_STATE_COMPLETED" },
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
      { kind: "status", state: "TASK_STATE_COMPLETED" },
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
      { kind: "status", state: "TASK_STATE_COMPLETED" },
    ]);
    const { result } = renderHook(() => useA2AChat({ streamFn }));

    await act(async () => {
      await result.current.send("help");
    });

    expect(result.current.turns).toHaveLength(2);
    expect(result.current.turns[1].text).toBe("");
    expect(result.current.turns[1].answer).toEqual(ANSWER);
  });

  it("removes the agent turn when the stream returns nothing", async () => {
    const streamFn = streamOf([
      { kind: "status", state: "TASK_STATE_COMPLETED" },
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
});
