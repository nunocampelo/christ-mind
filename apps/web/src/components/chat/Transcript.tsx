import { TurnRole, type Turn } from "@/hooks/useA2AChat";
import CitedAnswer from "@/components/chat/CitedAnswer";
import MarkdownMessage from "@/components/chat/MarkdownMessage";
import ReasoningTimeline from "@/components/chat/ReasoningTimeline";

interface TranscriptProps {
  turns: Turn[];
  busy: boolean;
  canReconnect?: boolean;
  onReconnect?: () => void;
  spacerHeight?: number;
}

const ReconnectChip = ({ onReconnect }: { onReconnect?: () => void }) => (
  <button
    type="button"
    data-testid="reconnect-chip"
    aria-label="Reconnect"
    onClick={onReconnect}
    className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95"
  >
    <svg
      viewBox="0 0 24 24"
      className="h-3.5 w-3.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21 12a9 9 0 1 1-3-6.7L21 8" />
      <path d="M21 3v5h-5" />
    </svg>
  </button>
);

const AgentTurn = ({ turn, busy }: { turn: Turn; busy: boolean }) => (
  <>
    <ReasoningTimeline steps={turn.steps} busy={busy} />
    {turn.answer ? (
      <CitedAnswer answer={turn.answer} streamedText={turn.text} />
    ) : (
      <MarkdownMessage text={turn.text} />
    )}
  </>
);

const Transcript = ({
  turns,
  busy,
  canReconnect,
  onReconnect,
  spacerHeight = 0,
}: TranscriptProps) => (
  <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
    {turns.map((turn, i) => {
      if (turn.role === TurnRole.user) {
        return (
          <div
            key={turn.id}
            data-turn
            data-role="user"
            data-testid="user-turn"
            className="self-end max-w-[85%] rounded-[var(--radius-app)] bg-muted px-4 py-2 text-foreground"
          >
            {turn.text}
          </div>
        );
      }
      if (turn.role === TurnRole.notice) {
        const isTail = i === turns.length - 1;
        return (
          <div
            key={turn.id}
            data-turn
            data-role="notice"
            data-testid="notice-turn"
            className="flex items-center self-start py-0.5 text-[0.6875rem] italic text-muted-foreground"
          >
            {turn.text}
            {isTail && canReconnect ? (
              <ReconnectChip onReconnect={onReconnect} />
            ) : null}
          </div>
        );
      }
      return (
        <div
          key={turn.id}
          data-turn
          data-role="agent"
          data-testid="agent-turn"
          className="self-start max-w-[95%] text-foreground"
        >
          <AgentTurn turn={turn} busy={busy && i === turns.length - 1} />
        </div>
      );
    })}
    <div
      data-testid="tail-spacer"
      aria-hidden="true"
      className={
        // Ease the collapse to 0 once idle so the reserved room settles smoothly; no
        // transition mid-stream (the spacer only changes on send, not per token).
        busy
          ? "shrink-0"
          : "shrink-0 transition-[height] duration-[250ms] ease motion-reduce:transition-none"
      }
      style={{ height: spacerHeight }}
    />
  </div>
);

export default Transcript;
