import { cn } from "@/lib/cn";

interface ScrollToBottomButtonProps {
  visible: boolean;
  onClick: () => void;
}

// Jump-to-bottom, rendered inside the composer (which owns its placement). Slides up +
// fades in when the transcript is scrolled up; gated with pointer-events/aria/tabIndex when
// hidden. Respects prefers-reduced-motion.
const ScrollToBottomButton = ({ visible, onClick }: ScrollToBottomButtonProps) => (
  <button
    type="button"
    data-testid="scroll-to-bottom"
    aria-label="Scroll to latest"
    aria-hidden={!visible}
    tabIndex={visible ? 0 : -1}
    onClick={onClick}
    className={cn(
      "absolute bottom-full right-0 mb-3 z-20",
      "flex h-9 w-9 items-center justify-center rounded-full",
      "border border-border bg-muted text-muted-foreground shadow-md",
      "transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-opacity",
      "hover:bg-muted hover:text-foreground",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      visible
        ? "translate-y-0 opacity-100"
        : "pointer-events-none translate-y-4 opacity-0 motion-reduce:translate-y-0",
    )}
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
      <path d="m6 9 6 6 6-6" />
    </svg>
  </button>
);

export default ScrollToBottomButton;
