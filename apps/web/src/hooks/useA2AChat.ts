import {
  type KeyboardEvent as ReactKeyboardEvent,
  useCallback,
  useRef,
  useState,
} from "react";
import {
  AgentEventKind,
  streamAssistant,
  type AgentAnswer,
  type AgentStreamEvent,
} from "@/api/agentApi";

const ENTER_KEY = "Enter";
const ERR_ASSISTANT_FAILED = "Assistant request failed";

const TurnRole = {
  user: "user",
  agent: "agent",
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
) => AsyncGenerator<AgentStreamEvent, void, void>;

const TERMINAL_STATES = new Set([
  "TASK_STATE_COMPLETED",
  "TASK_STATE_FAILED",
  "TASK_STATE_CANCELED",
]);

interface UseA2AChatOptions {
  streamFn?: StreamFn;
}

const useA2AChat = ({
  streamFn = streamAssistant,
}: UseA2AChatOptions = {}) => {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const inFlight = useRef(false);
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
    ) => {
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
            break;
          case AgentEventKind.status:
            if (event.text) appendStepToTurn(agentTurnId, event.text);
            if (TERMINAL_STATES.has(event.state)) return;
            break;
        }
      }
    },
    [appendStepToTurn, appendToAgentTurn, setAnswerOnTurn],
  );

  const send = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || busy || inFlight.current) return;

      inFlight.current = true;
      setBusy(true);
      setError(null);
      appendTurn({ role: TurnRole.user, text: trimmed, steps: [] });
      const agentTurnId = appendTurn({
        role: TurnRole.agent,
        text: "",
        steps: [],
      });

      try {
        await consumeStream(streamFn(trimmed), agentTurnId);
      } catch (err) {
        setError(err instanceof Error ? err.message : ERR_ASSISTANT_FAILED);
      } finally {
        removeAgentTurnIfEmpty(agentTurnId);
        setBusy(false);
        inFlight.current = false;
      }
    },
    [appendTurn, busy, consumeStream, removeAgentTurnIfEmpty, streamFn],
  );

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

  return {
    turns,
    busy,
    error,
    draft,
    setDraft,
    setError,
    send,
    handleSubmit,
    handleInputKeyDown,
  };
};

export default useA2AChat;
export { TurnRole };
export type { Turn };
