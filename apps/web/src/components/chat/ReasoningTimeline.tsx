import { useEffect, useRef, useState } from "react";
import "@/components/chat/chat.css";

interface ReasoningTimelineProps {
  steps: string[];
  busy: boolean;
}

const CALLING_PREFIX = "Calling ";

/** The last tool the agent named, for the collapsed summary — derived from the
    orchestrator's "Calling X" step labels. */
const latestTool = (steps: string[]): string | null => {
  for (let i = steps.length - 1; i >= 0; i--) {
    if (steps[i].startsWith(CALLING_PREFIX))
      return steps[i].slice(CALLING_PREFIX.length);
  }
  return null;
};

const stepCountLabel = (n: number): string => `${n} step${n === 1 ? "" : "s"}`;

/** The agent's tool-call/reasoning trace for one turn: the orchestrator's step
    milestones ("Mapped situation…", "Calling find_claims", "find_claims returned").
    Auto-expanded while the turn streams, auto-collapses once it settles — but a manual
    toggle in between is left alone. */
const ReasoningTimeline = ({ steps, busy }: ReasoningTimelineProps) => {
  const [open, setOpen] = useState(busy);
  const wasBusy = useRef(busy);

  useEffect(() => {
    if (wasBusy.current && !busy) setOpen(false);
    if (!wasBusy.current && busy) setOpen(true);
    wasBusy.current = busy;
  }, [busy]);

  if (steps.length === 0) return null;

  const tool = latestTool(steps);

  return (
    <details
      className="reasoning-panel"
      data-testid="reasoning-timeline"
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="reasoning-summary">
        <span className="reasoning-summary-label">Reasoning</span>
        <span className="reasoning-chip">{stepCountLabel(steps.length)}</span>
        {tool && <span className="reasoning-chip reasoning-chip-tool">{tool}</span>}
      </summary>
      <ol className="reasoning-steps">
        {steps.map((step, i) => (
          <li key={i} className="reasoning-step" data-testid="reasoning-step">
            <span className="reasoning-step-dot" aria-hidden="true" />
            <span className="reasoning-step-text">{step}</span>
          </li>
        ))}
      </ol>
    </details>
  );
};

export default ReasoningTimeline;
