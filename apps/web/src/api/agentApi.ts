import type { Artifact, Message, Part, StreamResponse } from "@a2a-js/sdk";
import { Role, TaskState } from "@a2a-js/sdk";
import {
  ClientFactory,
  ClientFactoryOptions,
  JsonRpcTransportFactory,
  type Client,
} from "@a2a-js/sdk/client";

const AgentEventKind = {
  status: "status",
  text: "text",
  answer: "answer",
  error: "error",
} as const;

const PayloadCase = {
  task: "task",
  message: "message",
  statusUpdate: "statusUpdate",
  artifactUpdate: "artifactUpdate",
} as const;

const PartCase = {
  text: "text",
} as const;

const ArtifactId = {
  answer: "answer",
  evidence: "evidence",
} as const;

interface CitedClaim {
  claim_id: string;
  source_id: string;
  subject: string;
  predicate: string;
  object: string | null;
  verb_phrase: string;
  evidence: string;
}

interface InferredChain {
  inferred: true;
  links: CitedClaim[];
}

interface AgentAnswer {
  text: string;
  concepts: string[];
  cited_claims: CitedClaim[];
  inferred_chains: InferredChain[];
}

type AgentStreamEvent =
  | { kind: typeof AgentEventKind.status; state: string; text: string }
  | { kind: typeof AgentEventKind.text; delta: string }
  | { kind: typeof AgentEventKind.answer; answer: AgentAnswer }
  | { kind: typeof AgentEventKind.error; message: string };

const ERR_ASSISTANT_FAILED = "Assistant request failed";
const ERR_MALFORMED_ANSWER = "Malformed answer payload";

const AGENT_BASE_URL =
  import.meta.env.VITE_AGENT_BASE_URL || globalThis.location.origin;

let clientPromise: Promise<Client> | null = null;

const buildClient = async (): Promise<Client> => {
  const factory = new ClientFactory(
    ClientFactoryOptions.createFrom(ClientFactoryOptions.default, {
      transports: [new JsonRpcTransportFactory({})],
    }),
  );
  return factory.createFromUrl(AGENT_BASE_URL);
};

const getClient = async (): Promise<Client> => {
  clientPromise ??= buildClient();
  try {
    return await clientPromise;
  } catch (error) {
    clientPromise = null;
    throw error;
  }
};

const newMessageId = (): string => crypto.randomUUID();

const isCitedClaim = (v: unknown): v is CitedClaim => {
  if (typeof v !== "object" || v === null) return false;
  const c = v as Record<string, unknown>;
  return (
    typeof c.claim_id === "string" &&
    typeof c.source_id === "string" &&
    typeof c.subject === "string" &&
    typeof c.predicate === "string" &&
    (typeof c.object === "string" || c.object === null) &&
    typeof c.verb_phrase === "string" &&
    typeof c.evidence === "string"
  );
};

const isInferredChain = (v: unknown): v is InferredChain => {
  if (typeof v !== "object" || v === null) return false;
  const chain = v as Record<string, unknown>;
  return (
    chain.inferred === true &&
    Array.isArray(chain.links) &&
    chain.links.every(isCitedClaim)
  );
};

const parseAgentAnswer = (json: string): AgentAnswer | null => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const a = parsed as Record<string, unknown>;
  if (
    typeof a.text !== "string" ||
    !Array.isArray(a.concepts) ||
    !a.concepts.every((c) => typeof c === "string") ||
    !Array.isArray(a.cited_claims) ||
    !a.cited_claims.every(isCitedClaim) ||
    !Array.isArray(a.inferred_chains) ||
    !a.inferred_chains.every(isInferredChain)
  ) {
    return null;
  }
  return parsed as AgentAnswer;
};

const partsText = (parts: Part[] | undefined): string => {
  if (!parts) return "";
  return parts
    .map((p: Part) =>
      p.content?.$case === PartCase.text ? p.content.value : "",
    )
    .join("");
};

const messageText = (message: Message | undefined): string =>
  partsText(message?.parts);

const artifactText = (artifact: Artifact | undefined): string =>
  partsText(artifact?.parts);

const eventsFromFrame = (frame: StreamResponse): AgentStreamEvent[] => {
  const payload = frame.payload;
  if (!payload) return [];
  const events: AgentStreamEvent[] = [];

  if (payload.$case === PayloadCase.task) {
    const task = payload.value;
    if (task.status?.state !== undefined) {
      events.push({
        kind: AgentEventKind.status,
        state: TaskState[task.status.state],
        text: "",
      });
    }
    return events;
  }

  if (payload.$case === PayloadCase.statusUpdate) {
    const update = payload.value;
    const state = update.status?.state;
    // On `working`, the orchestrator's step label ("Calling find_claims") rides here.
    const text = messageText(update.status?.message);

    if (state === TaskState.TASK_STATE_FAILED) {
      events.push(
        { kind: AgentEventKind.error, message: text || ERR_ASSISTANT_FAILED },
        { kind: AgentEventKind.status, state: TaskState[state], text: "" },
      );
      return events;
    }

    if (state !== undefined) {
      events.push({ kind: AgentEventKind.status, state: TaskState[state], text });
    }

    return events;
  }

  if (payload.$case === PayloadCase.artifactUpdate) {
    const artifact = payload.value.artifact;
    if (artifact?.artifactId === ArtifactId.evidence) {
      const answer = parseAgentAnswer(artifactText(artifact));
      events.push(
        answer
          ? { kind: AgentEventKind.answer, answer }
          : { kind: AgentEventKind.error, message: ERR_MALFORMED_ANSWER },
      );
      return events;
    }
    // "answer" (and any other id) streams prose; never silently drop text.
    const delta = artifactText(artifact);
    if (delta) events.push({ kind: AgentEventKind.text, delta });
    return events;
  }

  if (payload.$case === PayloadCase.message) {
    const delta = messageText(payload.value);
    if (delta) events.push({ kind: AgentEventKind.text, delta });
    return events;
  }

  return events;
};

async function* streamAssistant(
  message: string,
): AsyncGenerator<AgentStreamEvent, void, void> {
  const client = await getClient();

  const request = {
    tenant: "",
    message: {
      messageId: newMessageId(),
      role: Role.ROLE_USER,
      parts: [
        {
          content: { $case: PartCase.text, value: message },
          metadata: undefined,
          filename: "",
          mediaType: "",
        },
      ],
      contextId: "",
      taskId: "",
      metadata: undefined,
      extensions: [],
      referenceTaskIds: [],
    },
    configuration: undefined,
    metadata: undefined,
  };

  try {
    for await (const frame of client.sendMessageStream(request)) {
      for (const ev of eventsFromFrame(frame)) yield ev;
    }
  } catch (err) {
    yield {
      kind: AgentEventKind.error,
      message: err instanceof Error ? err.message : ERR_ASSISTANT_FAILED,
    };
  }
}

export {
  AgentEventKind,
  ArtifactId,
  eventsFromFrame,
  parseAgentAnswer,
  PartCase,
  PayloadCase,
  streamAssistant,
};
export type { AgentAnswer, AgentStreamEvent, CitedClaim, InferredChain };
