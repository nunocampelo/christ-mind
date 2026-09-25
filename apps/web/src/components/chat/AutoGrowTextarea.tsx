import {
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  useLayoutEffect,
  useRef,
} from "react";

interface AutoGrowTextareaProps {
  value: string;
  placeholder: string;
  disabled?: boolean;
  minRows?: number;
  maxRows?: number;
  className?: string;
  testId?: string;
  onChange: (value: string) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLTextAreaElement>) => void;
}

const DEFAULT_MAX_ROWS = 8;
const DEFAULT_MIN_ROWS = 1;
const FALLBACK_LINE_HEIGHT_PX = 24;

const AutoGrowTextarea = ({
  value,
  placeholder,
  disabled,
  minRows = DEFAULT_MIN_ROWS,
  maxRows = DEFAULT_MAX_ROWS,
  className,
  testId,
  onChange,
  onKeyDown,
}: AutoGrowTextareaProps) => {
  const ref = useRef<HTMLTextAreaElement>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    const parsedLineHeight = Number.parseFloat(
      globalThis.getComputedStyle(el).lineHeight,
    );
    const lineHeight = Number.isNaN(parsedLineHeight)
      ? FALLBACK_LINE_HEIGHT_PX
      : parsedLineHeight;
    const maxHeight = lineHeight * maxRows;
    const contentHeight = Math.min(el.scrollHeight, maxHeight);
    const minHeight = lineHeight * minRows + (el.offsetHeight - el.clientHeight);
    el.style.height = `${Math.max(contentHeight, minHeight)}px`;
    el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [value, minRows, maxRows]);

  return (
    <textarea
      ref={ref}
      className={className}
      data-testid={testId}
      value={value}
      placeholder={placeholder}
      disabled={disabled}
      rows={minRows}
      onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
    />
  );
};

export default AutoGrowTextarea;
