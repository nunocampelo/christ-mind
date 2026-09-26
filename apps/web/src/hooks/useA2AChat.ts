import {
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
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

const ENTER_KEY = "Enter";
const ERR_ASSISTANT_FAILED = "Assistant request failed";
const NOTICE_STOPPED = "Request stopped";
const CONTEXT_KEY = "christ-mind.agent.contextId";

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
  textSoFar: string,
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
}

const useA2AChat = ({
  streamFn = streamAssistant,
  recoverFn = recoverAssistant,
  onSend,
}: UseA2AChatOptions = {}) => {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const contextId = useRef(sessionStorage.getItem(CONTEXT_KEY) ?? "");
  const abortRef = useRef<AbortController | null>(null);
  const lastTaskId = useRef<string | null>(null);
  const lastAgentTurnId = useRef<number | null>(null);
  const turnsRef = useRef<Turn[]>(turns);
  turnsRef.current = turns;
  const nextTurnId = useRef(0);

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

  const appendStepToTurn = useCallback((id: number, text: string) => {
    setTurns((prev) =>
      prev.map((turn) =>
        turn.id === id ? { ...turn, steps: [...turn.steps, text] } : turn,
      ),
    );
  }, []);

  const setAnswerOnTurn = useCallback((id: number, answer: AgentAnswer) => {
    setTurns((prev) =>
      prev.map((turn) => (turn.id === id ? { ...turn, answer } : turn)),
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
    ): Promise<boolean> => {
      let errored = false;
      for await (const event of events) {
        switch (event.kind) {
          case AgentEventKind.text:
            appendToAgentTurn(agentTurnId, event.delta);
            break;
          case AgentEventKind.answer:
            setAnswerOnTurn(agentTurnId, event.answer);
            break;
          case AgentEventKind.error:
            setError(event.message);
            errored = true;
            break;
          case AgentEventKind.contextId:
            if (event.contextId) {
              contextId.current = event.contextId;
              sessionStorage.setItem(CONTEXT_KEY, event.contextId);
            }
            break;
          case AgentEventKind.taskId:
            if (event.taskId) lastTaskId.current = event.taskId;
            break;
          case AgentEventKind.status:
            if (event.text) appendStepToTurn(agentTurnId, event.text);
            if (TERMINAL_STATES.has(event.state)) return errored;
            break;
        }
      }
      return errored;
    },
    [appendStepToTurn, appendToAgentTurn, setAnswerOnTurn],
  );

  const send = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || busy || abortRef.current) return;

      const controller = new AbortController();
      abortRef.current = controller;
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
        );
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : ERR_ASSISTANT_FAILED);
        }
      } finally {
        removeAgentTurnIfEmpty(agentTurnId);
        setBusy(false);
        abortRef.current = null;
      }
    },
    [appendTurn, busy, consumeStream, onSend, removeAgentTurnIfEmpty, streamFn],
  );

  const handleCancel = useCallback(() => {
    const controller = abortRef.current;
    if (!controller) return;
    controller.abort();
    appendTurn({ role: TurnRole.notice, text: NOTICE_STOPPED, steps: [] });
  }, [appendTurn]);

  const removeTrailingNotices = useCallback(() => {
    setTurns((prev) => {
      let end = prev.length;
      while (end > 0 && prev[end - 1].role === TurnRole.notice) end--;
      return end === prev.length ? prev : prev.slice(0, end);
    });
  }, []);

  const handleReconnect = useCallback(async () => {
    const taskId = lastTaskId.current;
    const agentTurnId = lastAgentTurnId.current;
    if (!taskId || agentTurnId === null || busy || abortRef.current) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    const textSoFar =
      turnsRef.current.find((t) => t.id === agentTurnId)?.text ?? "";

    try {
      const errored = await consumeStream(recoverFn(taskId, textSoFar), agentTurnId);
      if (!errored) removeTrailingNotices();
    } catch (err) {
      setError(err instanceof Error ? err.message : ERR_ASSISTANT_FAILED);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }, [busy, consumeStream, recoverFn, removeTrailingNotices]);

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
