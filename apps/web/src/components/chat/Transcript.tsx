import { TurnRole, type Turn } from "@/hooks/useA2AChat";
import CitedAnswer from "@/components/chat/CitedAnswer";
import MarkdownMessage from "@/components/chat/MarkdownMessage";
import ReasoningTimeline from "@/components/chat/ReasoningTimeline";

interface TranscriptProps {
  turns: Turn[];
  busy: boolean;
}

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

const Transcript = ({ turns, busy }: TranscriptProps) => (
  <div className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
    {turns.map((turn, i) => {
      if (turn.role === TurnRole.user) {
        return (
          <div
            key={turn.id}
            data-testid="user-turn"
            className="self-end max-w-[85%] rounded-[var(--radius-app)] bg-muted px-4 py-2 text-foreground"
          >
            {turn.text}
          </div>
        );
      }
      if (turn.role === TurnRole.notice) {
        return (
          <div
            key={turn.id}
            data-testid="notice-turn"
            className="self-start py-0.5 text-[0.6875rem] italic text-muted-foreground"
          >
            {turn.text}
          </div>
        );
      }
      return (
        <div
          key={turn.id}
          data-testid="agent-turn"
          className="self-start max-w-[95%] text-foreground"
        >
          <AgentTurn turn={turn} busy={busy && i === turns.length - 1} />
        </div>
      );
    })}
  </div>
);

export default Transcript;
