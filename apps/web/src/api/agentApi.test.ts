import type { StreamResponse } from "@a2a-js/sdk";
import { TaskState } from "@a2a-js/sdk";
import { describe, expect, it } from "vitest";
import {
  AgentEventKind,
  eventsFromFrame,
  parseAgentAnswer,
  type AgentAnswer,
} from "@/api/agentApi";

const textPart = (value: string) => ({
  content: { $case: "text", value },
});

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
  inferred_chains: [
    {
      inferred: true,
      links: [
        {
          claim_id: "c1",
          source_id: "s1",
          subject: "the ego",
          predicate: "teaches",
          object: null,
          verb_phrase: "teaches",
          evidence: "The ego teaches attack.",
        },
      ],
    },
  ],
};

const frame = (payload: unknown): StreamResponse =>
  ({ payload }) as unknown as StreamResponse;

describe("eventsFromFrame", () => {
  it("maps a task frame to a status event", () => {
    const events = eventsFromFrame(
      frame({
        $case: "task",
        value: { status: { state: TaskState.TASK_STATE_WORKING } },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.status, state: "TASK_STATE_WORKING" },
    ]);
  });

  it("maps a working statusUpdate to a status event", () => {
    const events = eventsFromFrame(
      frame({
        $case: "statusUpdate",
        value: { status: { state: TaskState.TASK_STATE_WORKING } },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.status, state: "TASK_STATE_WORKING" },
    ]);
  });

  it("maps a FAILED statusUpdate to an error then a status event", () => {
    const events = eventsFromFrame(
      frame({
        $case: "statusUpdate",
        value: {
          status: {
            state: TaskState.TASK_STATE_FAILED,
            message: { parts: [textPart("boom")] },
          },
        },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.error, message: "boom" },
      { kind: AgentEventKind.status, state: "TASK_STATE_FAILED" },
    ]);
  });

  it("maps an answer artifact to a text delta", () => {
    const events = eventsFromFrame(
      frame({
        $case: "artifactUpdate",
        value: {
          artifact: { artifactId: "answer", parts: [textPart("Forgiveness ")] },
        },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.text, delta: "Forgiveness " },
    ]);
  });

  it("emits no event for an empty answer artifact chunk", () => {
    const events = eventsFromFrame(
      frame({
        $case: "artifactUpdate",
        value: { artifact: { artifactId: "answer", parts: [textPart("")] } },
      }),
    );
    expect(events).toEqual([]);
  });

  it("parses an evidence artifact into an answer event", () => {
    const events = eventsFromFrame(
      frame({
        $case: "artifactUpdate",
        value: {
          artifact: {
            artifactId: "evidence",
            parts: [textPart(JSON.stringify(ANSWER))],
          },
        },
      }),
    );
    expect(events).toEqual([{ kind: AgentEventKind.answer, answer: ANSWER }]);
  });

  it("emits an error (not a throw) for a malformed evidence artifact", () => {
    const events = eventsFromFrame(
      frame({
        $case: "artifactUpdate",
        value: {
          artifact: { artifactId: "evidence", parts: [textPart("{ not json")] },
        },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.error, message: "Malformed answer payload" },
    ]);
  });

  it("maps a message frame to a text delta", () => {
    const events = eventsFromFrame(
      frame({ $case: "message", value: { parts: [textPart("hi")] } }),
    );
    expect(events).toEqual([{ kind: AgentEventKind.text, delta: "hi" }]);
  });
});

describe("parseAgentAnswer", () => {
  it("returns the answer for valid JSON", () => {
    expect(parseAgentAnswer(JSON.stringify(ANSWER))).toEqual(ANSWER);
  });

  it("returns null for invalid JSON", () => {
    expect(parseAgentAnswer("{ not json")).toBeNull();
  });

  it("returns null when required arrays are missing", () => {
    expect(parseAgentAnswer(JSON.stringify({ text: "x" }))).toBeNull();
  });

  it("allows a cited claim with a null object", () => {
    const withNull: AgentAnswer = {
      ...ANSWER,
      cited_claims: [{ ...ANSWER.cited_claims[0], object: null }],
    };
    expect(parseAgentAnswer(JSON.stringify(withNull))).toEqual(withNull);
  });
});
