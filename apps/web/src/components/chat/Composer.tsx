import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import AutoGrowTextarea from "@/components/chat/AutoGrowTextarea";
import { Button } from "@/components/ui/button";

interface ComposerProps {
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown?: (event: ReactKeyboardEvent<HTMLTextAreaElement>) => void;
}

/** The sticky bottom input. In PR 1 send is inert (no sending yet); PR 2 wires
    onSubmit/onKeyDown to useA2AChat without reshaping this component. */
const Composer = ({
  value,
  disabled,
  onChange,
  onSubmit,
  onKeyDown,
}: ComposerProps) => {
  const canSend = !disabled && value.trim().length > 0;

  return (
    <div className="mx-auto w-full max-w-2xl px-4 pb-6">
      <div className="flex items-end gap-2 rounded-[var(--radius-app)] border border-border bg-muted/40 p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
        <AutoGrowTextarea
          testId="composer-input"
          value={value}
          placeholder="Describe a situation…"
          disabled={disabled}
          onChange={onChange}
          onKeyDown={onKeyDown ?? (() => {})}
          className="flex-1 resize-none bg-transparent px-2 py-1.5 text-base leading-6 text-foreground placeholder:text-muted-foreground focus:outline-none"
        />
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
      </div>
    </div>
  );
};

export default Composer;
