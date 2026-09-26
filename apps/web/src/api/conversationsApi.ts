import {
  AGENT_BASE_URL,
  validateAgentAnswer,
  type AgentAnswer,
} from "@/api/agentApi";
import { TurnRole, type Turn } from "@/hooks/useA2AChat";

// Wire shapes of the /conversations REST surface (mirrors the server's Conversation DTOs).
interface ConversationSummary {
  conversation_id: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
}

interface ConversationMessageDto {
  conversation_id: string;
  role: string;
  content: string;
  message_json: unknown;
  timestamp: string;
  sequence: number;
}

interface ConversationDetail {
  conversation_id: string;
  summary: string | null;
  created_at: string;
  updated_at: string;
  messages: ConversationMessageDto[];
}

const ERR_LOAD_FAILED = "Could not load conversation";
const ERR_RENAME_FAILED = "Could not rename conversation";
const ERR_DELETE_FAILED = "Could not delete conversation";

const listConversations = async (): Promise<ConversationSummary[]> => {
  const response = await fetch(`${AGENT_BASE_URL}/conversations`);
  if (!response.ok) throw new Error(ERR_LOAD_FAILED);
  return (await response.json()) as ConversationSummary[];
};

const renameConversation = async (id: string, summary: string): Promise<void> => {
  const response = await fetch(
    `${AGENT_BASE_URL}/conversations/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ summary }),
    },
  );
  if (!response.ok) throw new Error(ERR_RENAME_FAILED);
};

const deleteConversation = async (id: string): Promise<void> => {
  const response = await fetch(
    `${AGENT_BASE_URL}/conversations/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(ERR_DELETE_FAILED);
};

// Resolves to null on 404 (unknown/stale id) so callers can start a fresh conversation
// rather than surface an error; other failures throw.
const getConversation = async (
  id: string,
): Promise<ConversationDetail | null> => {
  const response = await fetch(
    `${AGENT_BASE_URL}/conversations/${encodeURIComponent(id)}`,
  );
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(ERR_LOAD_FAILED);
  return (await response.json()) as ConversationDetail;
};

const answerFrom = (message: ConversationMessageDto): AgentAnswer | undefined => {
  // A malformed stored answer (older/other client) degrades to prose-only, never a crash.
  return validateAgentAnswer(message.message_json) ?? undefined;
};

// Rebuild the transcript from stored history. Pure (no fetch) so it's unit-testable with
// injected DTOs. `steps` stay empty: the live reasoning trace isn't persisted, so a
// rehydrated agent turn shows prose + citations + evidence, not the working labels.
const turnsFromConversation = (detail: ConversationDetail): Turn[] =>
  detail.messages.map((message, index) => {
    const isAgent = message.role === TurnRole.agent;
    return {
      id: index,
      role: isAgent ? TurnRole.agent : TurnRole.user,
      text: message.content,
      steps: [],
      answer: isAgent ? answerFrom(message) : undefined,
    };
  });

export {
  deleteConversation,
  getConversation,
  listConversations,
  renameConversation,
  turnsFromConversation,
};
export type { ConversationDetail, ConversationMessageDto, ConversationSummary };
