import { describe, expect, it } from "vitest";
import type { AgentAnswer } from "@/api/agentApi";
import {
  turnsFromConversation,
  type ConversationDetail,
} from "@/api/conversationsApi";
import { TurnRole } from "@/hooks/useA2AChat";

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
    },
  ],
  inferred_chains: [],
};

const detailWith = (
  messages: ConversationDetail["messages"],
): ConversationDetail => ({
  conversation_id: "ctx-1",
  summary: "a thread",
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
  messages,
});

const userMsg = (content: string, sequence: number) => ({
  conversation_id: "ctx-1",
  role: "user",
  content,
  message_json: null,
  timestamp: "2026-01-01T00:00:00",
  sequence,
});

const agentMsg = (content: string, message_json: unknown, sequence: number) => ({
  conversation_id: "ctx-1",
  role: "agent",
  content,
  message_json,
  timestamp: "2026-01-01T00:00:00",
  sequence,
});

describe("turnsFromConversation", () => {
  it("rebuilds user and agent turns in order with contiguous ids", () => {
    const turns = turnsFromConversation(
      detailWith([
        userMsg("I can't forgive", 1),
        agentMsg("Forgiveness undoes it.", ANSWER, 2),
      ]),
    );

    expect(turns.map((t) => [t.id, t.role, t.text])).toEqual([
      [0, TurnRole.user, "I can't forgive"],
      [1, TurnRole.agent, "Forgiveness undoes it."],
    ]);
    expect(turns[0].steps).toEqual([]);
    expect(turns[1].steps).toEqual([]);
  });

  it("carries the parsed answer onto the agent turn, none on the user turn", () => {
    const turns = turnsFromConversation(
      detailWith([userMsg("help", 1), agentMsg("prose", ANSWER, 2)]),
    );
    expect(turns[0].answer).toBeUndefined();
    expect(turns[1].answer).toEqual(ANSWER);
  });

  it("degrades a malformed agent answer to prose-only rather than crashing", () => {
    const turns = turnsFromConversation(
      detailWith([agentMsg("prose survives", { not: "an answer" }, 1)]),
    );
    expect(turns[0].text).toBe("prose survives");
    expect(turns[0].answer).toBeUndefined();
  });

  it("returns no turns for an empty conversation", () => {
    expect(turnsFromConversation(detailWith([]))).toEqual([]);
  });
});
