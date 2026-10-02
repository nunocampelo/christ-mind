import type { Artifact, Message, Part, StreamResponse, Task } from "@a2a-js/sdk";
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
  contextId: "contextId",
  taskId: "taskId",
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
  book: string;
  chapter: number;
  verse: number | null;
  section: number | null;
  paragraph: number | null;
  edition: string;
  subject: string;
  predicate: string;
  object: string | null;
  verb_phrase: string;
  polarity: string;
  evidence: string;
  // The source paragraph the claim was drawn from; "" when the source couldn't be fetched.
  // evidence_start/evidence_end index evidence_context (NOT evidence): the marked clause is
  // evidence_context.slice(evidence_start, evidence_end) === evidence.
  evidence_context: string;
  evidence_start: number;
  evidence_end: number;
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
  // `replace` carries the server's final sanitized answer (fabricated markers stripped),
  // which arrives as a non-append artifact chunk and supersedes the raw streamed deltas.
  | { kind: typeof AgentEventKind.text; delta: string; replace?: boolean }
  | { kind: typeof AgentEventKind.answer; answer: AgentAnswer }
  | { kind: typeof AgentEventKind.error; message: string }
  | { kind: typeof AgentEventKind.contextId; contextId: string }
  | { kind: typeof AgentEventKind.taskId; taskId: string };

const ERR_ASSISTANT_FAILED = "Assistant request failed";
const ERR_MALFORMED_ANSWER = "Malformed answer payload";
const ERR_RECOVER_TIMEOUT = "Could not recover the answer";

const RECOVER_POLL_MS = 500;
// A client disconnect does not cancel the run (the SDK keeps consuming server-side), so a
// reconnect is usually waiting on a task that is still legitimately working. The budget must
// therefore exceed a full orchestrator run, not a snappy one: up to max_steps (6) LLM
// round-trips plus tool calls routinely reach ~25s and can run longer. 360 polls * 500ms =
// 180s of headroom; a shorter budget abandons the task right before it settles and surfaces
// a spurious "could not recover" while the answer is in fact completing.
const RECOVER_MAX_POLLS = 360;

const TERMINAL_STATES = new Set([
  TaskState.TASK_STATE_COMPLETED,
  TaskState.TASK_STATE_FAILED,
  TaskState.TASK_STATE_CANCELED,
]);

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
    typeof c.polarity === "string" &&
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

// A prose segment is either plain text (rendered as markdown) or a citation: an inline
// [claim_id] marker the agent wrote, resolved to the claim it points at. The ordinal is
// assigned by first appearance so the reader sees ¹ ² ..., not raw ids. An unknown or
// malformed marker never becomes a segment -- it is dropped, never shown as literal
// "[...]" (the agent's soft validation is the strict layer; here we only render).
// `claim` is null only mid-stream: the prose (with markers) streams before the evidence
// artifact carrying the claims lands, so the superscript renders immediately (numbered by
// appearance) and gains its source link once the claim resolves.
type ProseSegment =
  | { kind: "text"; text: string }
  | { kind: "citation"; claim: CitedClaim | null; ordinal: number };

// A claim_id as written in a marker: id chars only, no whitespace (mirrors the agent's
// definition in domain/citations.py, so both layers agree on what a marker is).
const MARKER = /\[([A-Za-z0-9][A-Za-z0-9._-]*)\]/g;

// `pending` = the prose is still streaming, so the claims haven't arrived yet. Every
// well-formed marker becomes a citation segment keyed by its raw id (claim null), so the
// superscript renders immediately; ids are numbered by first appearance, matching what the
// resolved pass will assign once the same markers resolve to claims. Off (the default,
// final render), an unresolved marker is a genuine hallucination and is dropped.
const parseCitedProse = (
  text: string,
  citedClaims: CitedClaim[],
  pending = false,
): ProseSegment[] => {
  const byId = new Map(citedClaims.map((c) => [c.claim_id, c]));
  const ordinals = new Map<string, number>();
  const segments: ProseSegment[] = [];
  let cursor = 0;

  for (const match of text.matchAll(MARKER)) {
    const before = text.slice(cursor, match.index);
    if (before) segments.push({ kind: "text", text: before });
    cursor = match.index + match[0].length;

    const id = match[1];
    const claim = byId.get(id) ?? null;
    // Final render: an id with no claim is malformed (the agent's soft audit already
    // recorded it) -- strip it, never leave a literal "[id]" in the reader-facing prose.
    if (!claim && !pending) continue;

    let ordinal = ordinals.get(id);
    if (ordinal === undefined) {
      ordinal = ordinals.size + 1;
      ordinals.set(id, ordinal);
    }
    segments.push({ kind: "citation", claim, ordinal });
  }

  const tail = text.slice(cursor);
  if (tail) segments.push({ kind: "text", text: tail });
  return segments;
};

// Prose with each citation marker rewritten to its reader-facing ordinal ("[1]", "[2]"),
// numbered by first appearance to match the rendered superscripts. Text for copying; the
// source list that resolves the ordinals is appended by copyTextForAnswer (copyAnswer.ts).
const citedProseToPlainText = (text: string, claims: CitedClaim[]): string =>
  parseCitedProse(text, claims)
    .map((seg) => (seg.kind === "text" ? seg.text : `[${seg.ordinal}]`))
    .join("")
    .replace(/ +([.,;:!?])/g, "$1")
    .replace(/[ \t]{2,}/g, " ");

const validateAgentAnswer = (value: unknown): AgentAnswer | null => {
  if (typeof value !== "object" || value === null) return null;
  const a = value as Record<string, unknown>;
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
  return value as AgentAnswer;
};

const parseAgentAnswer = (json: string): AgentAnswer | null => {
  try {
    return validateAgentAnswer(JSON.parse(json));
  } catch {
    return null;
  }
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
    if (task.contextId) {
      events.push({ kind: AgentEventKind.contextId, contextId: task.contextId });
    }
    if (task.id) {
      events.push({ kind: AgentEventKind.taskId, taskId: task.id });
    }
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
    // "answer" (and any other id) streams prose; never silently drop text. The final chunk
    // (`lastChunk`) carries the server's sanitized full answer and replaces what streamed so
    // far, so the raw deltas (which may carry fabricated markers) are superseded, not added
    // to; interior chunks append as usual.
    const delta = artifactText(artifact);
    const replace = payload.value.lastChunk === true;
    if (replace) events.push({ kind: AgentEventKind.text, delta, replace });
    else if (delta) events.push({ kind: AgentEventKind.text, delta });
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
  contextId = "",
  signal?: AbortSignal,
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
      contextId,
      taskId: "",
      metadata: undefined,
      extensions: [],
      referenceTaskIds: [],
    },
    configuration: undefined,
    metadata: undefined,
  };

  try {
    for await (const frame of client.sendMessageStream(request, { signal })) {
      for (const ev of eventsFromFrame(frame)) yield ev;
    }
  } catch (err) {
    if (signal?.aborted) return;
    yield {
      kind: AgentEventKind.error,
      message: err instanceof Error ? err.message : ERR_ASSISTANT_FAILED,
    };
  }
}

// Resolve-and-exit on abort (not reject): the poll loop re-checks the signal on the next
// iteration and returns cleanly, so an aborted wait just wakes early rather than throwing.
const sleep = (ms: number, signal?: AbortSignal): Promise<void> =>
  new Promise((resolve) => {
    if (signal?.aborted) return resolve();
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      resolve();
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });

const findArtifact = (task: Task, id: string): Artifact | undefined =>
  task.artifacts.find((a) => a.artifactId === id);

// Map a *terminal* task into the events that refill a dropped bubble: the authoritative
// answer (replacing whatever partially streamed before the drop), then the parsed evidence,
// then the terminal status. FAILED maps to an error. The stored answer artifact is the
// sanitized final text (the executor replaces the raw deltas with it), so recovery emits it
// as a single `replace` rather than diffing against what streamed. The polling in
// `recoverAssistant` calls this once the task settles; kept pure (no client) so it is
// unit-testable in isolation.
function* recoverEventsFromTask(
  task: Task,
): Generator<AgentStreamEvent, void, void> {
  const state = task.status?.state;
  if (state === undefined) return;

  if (state === TaskState.TASK_STATE_FAILED) {
    const message = messageText(task.status?.message);
    yield { kind: AgentEventKind.error, message: message || ERR_ASSISTANT_FAILED };
    yield { kind: AgentEventKind.status, state: TaskState[state], text: "" };
    return;
  }

  const full = artifactText(findArtifact(task, ArtifactId.answer));
  yield { kind: AgentEventKind.text, delta: full, replace: true };

  const evidence = findArtifact(task, ArtifactId.evidence);
  if (evidence) {
    const answer = parseAgentAnswer(artifactText(evidence));
    yield answer
      ? { kind: AgentEventKind.answer, answer }
      : { kind: AgentEventKind.error, message: ERR_MALFORMED_ANSWER };
  }

  yield { kind: AgentEventKind.status, state: TaskState[state], text: "" };
}

// Replay a dropped stream by polling GetTask until the task reaches a terminal state, then
// emitting its recovered events (see `recoverEventsFromTask`), so the reconnect refills the
// same bubble rather than duplicating its prose. A disconnect does not cancel the run, so a
// recovered task is usually still WORKING: each poll re-surfaces the live progress GetTask
// carries -- the current working-step label (status.message) and the partial answer artifact
// -- so the reasoning timeline keeps advancing and the bubble shows live prose instead of
// sitting silent until the task settles. Both are deduped against what was last emitted (the
// label and the artifact repeat verbatim across polls), and the partial prose rides as a
// `replace` so each emission overwrites rather than appends; the terminal pass then replaces
// it once more with the authoritative sanitized answer.
async function* recoverAssistant(
  taskId: string,
  signal?: AbortSignal,
): AsyncGenerator<AgentStreamEvent, void, void> {
  const client = await getClient();
  let lastStep = "";
  let lastPartial = "";

  for (let poll = 0; poll < RECOVER_MAX_POLLS; poll++) {
    if (signal?.aborted) return;
    let task: Task;
    try {
      task = await client.getTask({ tenant: "", id: taskId }, { signal });
    } catch (err) {
      if (signal?.aborted) return;
      yield {
        kind: AgentEventKind.error,
        message: err instanceof Error ? err.message : ERR_ASSISTANT_FAILED,
      };
      return;
    }

    const state = task.status?.state;
    if (state === undefined || !TERMINAL_STATES.has(state)) {
      const step = messageText(task.status?.message);
      if (step && step !== lastStep) {
        lastStep = step;
        yield { kind: AgentEventKind.status, state: TaskState[state ?? 0], text: step };
      }
      const partial = artifactText(findArtifact(task, ArtifactId.answer));
      if (partial && partial !== lastPartial) {
        lastPartial = partial;
        yield { kind: AgentEventKind.text, delta: partial, replace: true };
      }
      await sleep(RECOVER_POLL_MS, signal);
      continue;
    }

    yield* recoverEventsFromTask(task);
    return;
  }

  yield { kind: AgentEventKind.error, message: ERR_RECOVER_TIMEOUT };
}

export {
  AGENT_BASE_URL,
  AgentEventKind,
  ArtifactId,
  citedProseToPlainText,
  eventsFromFrame,
  parseAgentAnswer,
  parseCitedProse,
  PartCase,
  PayloadCase,
  recoverAssistant,
  recoverEventsFromTask,
  streamAssistant,
  validateAgentAnswer,
};
export type {
  AgentAnswer,
  AgentStreamEvent,
  CitedClaim,
  InferredChain,
  ProseSegment,
};
