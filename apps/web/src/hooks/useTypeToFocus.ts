import { useEffect, type RefObject } from "react";

// Focuses the composer when the user starts typing a printable character anywhere on the
// page (nothing else focused). Focusing on keydown without preventDefault lets the browser
// deliver that same character into the now-focused textarea, so the first keystroke isn't
// dropped. Modifier combos (Cmd/Ctrl shortcuts) and navigation keys are ignored, as is
// typing that's already headed for an input, textarea, or editable element.
const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT"
  );
};

const useTypeToFocus = (ref: RefObject<HTMLTextAreaElement | null>): void => {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.length !== 1) return;
      if (isEditableTarget(event.target)) return;
      ref.current?.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [ref]);
};

export default useTypeToFocus;
