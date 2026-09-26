import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import AutoGrowTextarea from "@/components/chat/AutoGrowTextarea";
import { Button } from "@/components/ui/button";

interface ComposerProps {
  value: string;
  busy?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel?: () => void;
  onKeyDown?: (event: ReactKeyboardEvent<HTMLTextAreaElement>) => void;
  /** Floating overlay (the jump-to-bottom button) positioned above the input row. */
  overlay?: ReactNode;
}

/** The sticky bottom input. The textarea stays usable while a request streams (the user can
    draft their next message); only sending is suppressed — the send button becomes a stop
    button that aborts the run (PR 5), and Enter no-ops via the hook's busy guard. */
const Composer = ({
  value,
  busy,
  onChange,
  onSubmit,
  onCancel,
  onKeyDown,
  overlay,
}: ComposerProps) => {
  const canSend = value.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-2xl px-4 pb-6">
      <div className="relative flex items-end gap-2 rounded-[var(--radius-app)] border border-border bg-muted/40 p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
        {overlay}
        <AutoGrowTextarea
          testId="composer-input"
          value={value}
          placeholder="Describe a situation…"
          onChange={onChange}
          onKeyDown={onKeyDown ?? (() => {})}
          className="flex-1 resize-none bg-transparent px-2 py-1.5 text-base leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
        {busy ? (
          <Button
            data-testid="composer-stop"
            aria-label="Stop"
            onClick={onCancel}
            className="h-9 w-9 shrink-0"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="currentColor"
              aria-hidden="true"
            >
              <rect x="6" y="6" width="12" height="12" rx="1.5" />
            </svg>
          </Button>
        ) : (
          <Button
            data-testid="composer-send"
            aria-label="Send"
            disabled={!canSend}
            onClick={onSubmit}
            className="h-9 w-9 shrink-0"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 19V5" />
              <path d="m5 12 7-7 7 7" />
            </svg>
          </Button>
        )}
      </div>
    </div>
  );
};

export default Composer;
