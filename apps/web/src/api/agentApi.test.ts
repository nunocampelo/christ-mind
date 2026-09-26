import type { StreamResponse } from "@a2a-js/sdk";
import { TaskState } from "@a2a-js/sdk";
import { describe, expect, it } from "vitest";
import {
  AgentEventKind,
  eventsFromFrame,
  parseAgentAnswer,
  parseCitedProse,
  type AgentAnswer,
  type CitedClaim,
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
      polarity: "affirmed",
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
          polarity: "affirmed",
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
      { kind: AgentEventKind.status, state: "TASK_STATE_WORKING", text: "" },
    ]);
  });

  it("emits a context id event before the status when the task frame carries one", () => {
    const events = eventsFromFrame(
      frame({
        $case: "task",
        value: {
          contextId: "ctx-1",
          status: { state: TaskState.TASK_STATE_WORKING },
        },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.contextId, contextId: "ctx-1" },
      { kind: AgentEventKind.status, state: "TASK_STATE_WORKING", text: "" },
    ]);
  });

  it("omits the context id event when the task frame has none", () => {
    const events = eventsFromFrame(
      frame({
        $case: "task",
        value: {
          contextId: "",
          status: { state: TaskState.TASK_STATE_WORKING },
        },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.status, state: "TASK_STATE_WORKING", text: "" },
    ]);
  });

  it("maps a working statusUpdate with no message to an empty-text status event", () => {
    const events = eventsFromFrame(
      frame({
        $case: "statusUpdate",
        value: { status: { state: TaskState.TASK_STATE_WORKING } },
      }),
    );
    expect(events).toEqual([
      { kind: AgentEventKind.status, state: "TASK_STATE_WORKING", text: "" },
    ]);
  });

  it("carries the step label from a working statusUpdate message", () => {
    const events = eventsFromFrame(
      frame({
        $case: "statusUpdate",
        value: {
          status: {
            state: TaskState.TASK_STATE_WORKING,
            message: { parts: [textPart("Calling find_claims")] },
          },
        },
      }),
    );
    expect(events).toEqual([
      {
        kind: AgentEventKind.status,
        state: "TASK_STATE_WORKING",
        text: "Calling find_claims",
      },
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
      { kind: AgentEventKind.status, state: "TASK_STATE_FAILED", text: "" },
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

describe("parseCitedProse", () => {
  const claim = (claim_id: string): CitedClaim => ({
    claim_id,
    source_id: `s-${claim_id}`,
    subject: "God",
    predicate: "is",
    object: "the Giver of life",
    verb_phrase: "is",
    polarity: "affirmed",
    evidence: "God is the Giver of life.",
  });

  it("resolves a known marker to a numbered citation segment", () => {
    const segments = parseCitedProse("God is the Giver of life. [c1]", [
      claim("c1"),
    ]);
    expect(segments).toEqual([
      { kind: "text", text: "God is the Giver of life. " },
      { kind: "citation", claim: claim("c1"), ordinal: 1 },
    ]);
  });

  it("drops an unknown marker rather than showing it literally", () => {
    const segments = parseCitedProse("Grounded. [nope] More.", [claim("c1")]);
    const text = segments
      .filter((s) => s.kind === "text")
      .map((s) => (s.kind === "text" ? s.text : ""))
      .join("");
    expect(text).not.toContain("[nope]");
    expect(segments.every((s) => s.kind === "text")).toBe(true);
  });

  it("numbers distinct claims by first appearance and reuses a claim's ordinal", () => {
    const segments = parseCitedProse("A [c1] B [c2] C [c1]", [
      claim("c1"),
      claim("c2"),
    ]);
    const ordinals = segments
      .filter((s) => s.kind === "citation")
      .map((s) => (s.kind === "citation" ? s.ordinal : 0));
    expect(ordinals).toEqual([1, 2, 1]);
  });
});
