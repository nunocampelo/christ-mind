import {
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  AgentEventKind,
  recoverAssistant,
  streamAssistant,
  type AgentAnswer,
  type AgentStreamEvent,
} from "@/api/agentApi";
import { CONTEXT_KEY } from "@/lib/session";

const ENTER_KEY = "Enter";
const ERR_ASSISTANT_FAILED = "Assistant request failed";
const NOTICE_STOPPED = "Request stopped";

const TurnRole = {
  user: "user",
  agent: "agent",
  notice: "notice",
} as const;

interface Turn {
  id: number;
  role: (typeof TurnRole)[keyof typeof TurnRole];
  text: string;
  steps: string[];
  answer?: AgentAnswer;
}

type StreamFn = (
  message: string,
  contextId: string,
  signal?: AbortSignal,
) => AsyncGenerator<AgentStreamEvent, void, void>;

type RecoverFn = (
  taskId: string,
  signal?: AbortSignal,
) => AsyncGenerator<AgentStreamEvent, void, void>;

const TERMINAL_STATES = new Set([
  "TASK_STATE_COMPLETED",
  "TASK_STATE_FAILED",
  "TASK_STATE_CANCELED",
]);

interface UseA2AChatOptions {
  streamFn?: StreamFn;
  recoverFn?: RecoverFn;
  onSend?: () => void;
  // Rehydration seeds (default: empty / sessionStorage), so a reload can restore a
  // conversation. `initialTurns` must carry contiguous ids 0..n-1 (turnsFromConversation
  // does), since nextTurnId resumes past them.
  initialContextId?: string;
  initialTurns?: Turn[];
  // Fires once the server assigns a conversation's id (the A2A contextId) on the first
  // turn of a fresh chat, so App can route to /c/:id and refresh the sidebar list.
  onConversationId?: (conversationId: string) => void;
}

const useA2AChat = ({
  streamFn = streamAssistant,
  recoverFn = recoverAssistant,
  onSend,
  initialContextId,
  initialTurns,
  onConversationId,
}: UseA2AChatOptions = {}) => {
  const [turns, setTurns] = useState<Turn[]>(initialTurns ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const contextId = useRef(
    initialContextId ?? sessionStorage.getItem(CONTEXT_KEY) ?? "",
  );
  const abortRef = useRef<AbortController | null>(null);
  const lastTaskId = useRef<string | null>(null);
  const lastAgentTurnId = useRef<number | null>(null);
  const turnsRef = useRef<Turn[]>(turns);
  turnsRef.current = turns;
  const nextTurnId = useRef(initialTurns?.length ?? 0);

  useEffect(() => () => abortRef.current?.abort(), []);

  const appendTurn = useCallback((turn: Omit<Turn, "id">): number => {
    const id = nextTurnId.current++;
    setTurns((prev) => [...prev, { ...turn, id }]);
    return id;
  }, []);

  const appendToAgentTurn = useCallback((id: number, delta: string) => {
    setTurns((prev) =>
      prev.map((turn) =>
        turn.id === id ? { ...turn, text: turn.text + delta } : turn,
      ),
    );
  }, []);

  const setTextOnAgentTurn = useCallback((id: number, text: string) => {
    setTurns((prev) =>
      prev.map((turn) => (turn.id === id ? { ...turn, text } : turn)),
    );
  }, []);

  const appendStepToTurn = useCallback((id: number, text: string) => {
    setTurns((prev) =>
      prev.map((turn) =>
        // Skip a label identical to the turn's current last step: recovery re-polls the same
        // working status across polls, so the live step must not be appended twice.
        turn.id === id && turn.steps.at(-1) !== text
          ? { ...turn, steps: [...turn.steps, text] }
          : turn,
      ),
    );
  }, []);

  const setAnswerOnTurn = useCallback((id: number, answer: AgentAnswer) => {
    setTurns((prev) =>
      prev.map((turn) => (turn.id === id ? { ...turn, answer } : turn)),
    );
  }, []);

  const resetAgentTurn = useCallback((id: number) => {
    setTurns((prev) =>
      prev.map((turn) =>
        turn.id === id
          ? { ...turn, text: "", steps: [], answer: undefined }
          : turn,
      ),
    );
  }, []);

  const removeAgentTurnIfEmpty = useCallback((id: number) => {
    setTurns((prev) =>
      prev.filter(
        (turn) =>
          !(
            turn.id === id &&
            turn.text === "" &&
            turn.answer === undefined &&
            turn.steps.length === 0
          ),
      ),
    );
  }, []);

  const consumeStream = useCallback(
    async (
      events: AsyncGenerator<AgentStreamEvent, void, void>,
      agentTurnId: number,
      controller: AbortController,
    ): Promise<boolean> => {
      let errored = false;
      for await (const event of events) {
        // A superseded run's generator can keep yielding after a newer send replaced it;
        // bail before touching shared refs (contextId/taskId) or this run's turn so a late
        // event can't clobber the live run. Return (not continue) to stop draining promptly.
        if (abortRef.current !== controller) return errored;
        switch (event.kind) {
          case AgentEventKind.text:
            if (event.replace) setTextOnAgentTurn(agentTurnId, event.delta);
            else appendToAgentTurn(agentTurnId, event.delta);
            break;
          case AgentEventKind.answer:
            setAnswerOnTurn(agentTurnId, event.answer);
            break;
          case AgentEventKind.error:
            setError(event.message);
            errored = true;
            break;
          case AgentEventKind.contextId:
            if (event.contextId && event.contextId !== contextId.current) {
              // New id: the server just created this conversation (a fresh chat's first
              // turn). Notify so App can route to it; a turn in an already-routed
              // conversation echoes the same id and doesn't re-fire.
              contextId.current = event.contextId;
              sessionStorage.setItem(CONTEXT_KEY, event.contextId);
              onConversationId?.(event.contextId);
            }
            break;
          case AgentEventKind.taskId:
            if (event.taskId) lastTaskId.current = event.taskId;
            break;
          case AgentEventKind.status: {
            // Only `working`-state labels are reasoning steps. The terminal `complete`
            // message re-carries the full answer prose (for non-streaming clients); the
            // streaming client already has it as prose + the structured answer, so
            // appending it here would render the whole answer a second time as a step.
            const terminal = TERMINAL_STATES.has(event.state);
            if (event.text && !terminal) appendStepToTurn(agentTurnId, event.text);
            if (terminal) return errored;
            break;
          }
        }
      }
      return errored;
    },
    [
      appendStepToTurn,
      appendToAgentTurn,
      setTextOnAgentTurn,
      onConversationId,
      setAnswerOnTurn,
    ],
  );

  const send = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || busy || abortRef.current) return;

      const controller = new AbortController();
      abortRef.current = controller;
      lastTaskId.current = null;
      lastAgentTurnId.current = null;
      setBusy(true);
      setError(null);
      appendTurn({ role: TurnRole.user, text: trimmed, steps: [] });
      const agentTurnId = appendTurn({
        role: TurnRole.agent,
        text: "",
        steps: [],
      });
      lastAgentTurnId.current = agentTurnId;
      onSend?.();

      try {
        await consumeStream(
          streamFn(trimmed, contextId.current, controller.signal),
          agentTurnId,
          controller,
        );
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : ERR_ASSISTANT_FAILED);
        }
      } finally {
        // handleCancel clears the in-flight guards synchronously and may already have
        // started a newer run; only tear down if this run still owns them, so a stopped
        // stream unwinding late can't clobber the run that replaced it.
        if (abortRef.current === controller) {
          removeAgentTurnIfEmpty(agentTurnId);
          setBusy(false);
          abortRef.current = null;
        }
      }
    },
    [appendTurn, busy, consumeStream, onSend, removeAgentTurnIfEmpty, streamFn],
  );

  const handleCancel = useCallback(() => {
    const controller = abortRef.current;
    if (!controller) return;
    controller.abort();
    // Clear the in-flight guards here rather than waiting for the aborted stream to
    // unwind: the A2A client's iterator may not react to the signal promptly, and a hung
    // generator would leave `busy`/`abortRef` stuck and block every retry. Dropping the
    // empty bubble mirrors what the run's `finally` would have done.
    abortRef.current = null;
    setBusy(false);
    if (lastAgentTurnId.current !== null) {
      removeAgentTurnIfEmpty(lastAgentTurnId.current);
    }
    appendTurn({ role: TurnRole.notice, text: NOTICE_STOPPED, steps: [] });
  }, [appendTurn, removeAgentTurnIfEmpty]);

  const removeTrailingNotices = useCallback(() => {
    setTurns((prev) => {
      let end = prev.length;
      while (end > 0 && prev[end - 1].role === TurnRole.notice) end--;
      return end === prev.length ? prev : prev.slice(0, end);
    });
  }, []);

  const handleReconnect = useCallback(async () => {
    const taskId = lastTaskId.current;
    if (!taskId || busy || abortRef.current) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);

    // Reconnect presents like a fresh send: strip the trailing "Request stopped" notice and
    // clear the carried-over bubble back to empty (loading star), so the stale reasoning and
    // partial prose from the stopped attempt disappear until recovery refills them. Stopping
    // before the first token removes the empty bubble entirely, so recreate it in that case
    // or the recovered reply would be written to a missing id and never render.
    removeTrailingNotices();
    const existing = turnsRef.current.find(
      (t) => t.id === lastAgentTurnId.current && t.role === TurnRole.agent,
    );
    let agentTurnId: number;
    if (existing) {
      agentTurnId = existing.id;
      resetAgentTurn(agentTurnId);
    } else {
      agentTurnId = appendTurn({ role: TurnRole.agent, text: "", steps: [] });
    }
    lastAgentTurnId.current = agentTurnId;

    try {
      const errored = await consumeStream(
        recoverFn(taskId, controller.signal),
        agentTurnId,
        controller,
      );
      // The notice was stripped up-front for the fresh-send look; a failed recovery restores
      // it so its reconnect chip returns and the user can retry again.
      if (errored) appendTurn({ role: TurnRole.notice, text: NOTICE_STOPPED, steps: [] });
    } catch (err) {
      setError(err instanceof Error ? err.message : ERR_ASSISTANT_FAILED);
      appendTurn({ role: TurnRole.notice, text: NOTICE_STOPPED, steps: [] });
    } finally {
      if (abortRef.current === controller) {
        setBusy(false);
        abortRef.current = null;
      }
    }
  }, [
    appendTurn,
    busy,
    consumeStream,
    recoverFn,
    removeTrailingNotices,
    resetAgentTurn,
  ]);

  const handleSubmit = useCallback(() => {
    if (busy) return;
    const value = draft;
    setDraft("");
    void send(value);
  }, [busy, draft, send]);

  const handleInputKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLElement>) => {
      if (event.key === ENTER_KEY && !event.shiftKey) {
        event.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const canReconnect = !busy && lastTaskId.current !== null;

  return {
    turns,
    busy,
    error,
    draft,
    canReconnect,
    setDraft,
    setError,
    send,
    handleSubmit,
    handleInputKeyDown,
    handleCancel,
    handleReconnect,
  };
};

export default useA2AChat;
export { TurnRole };
export type { Turn };
