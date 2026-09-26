import { useCallback, useEffect, useState, type RefObject } from "react";

const AT_BOTTOM_THRESHOLD = 24;

interface ScrollToBottom {
  isAtBottom: boolean;
  scrollToBottom: () => void;
}

// Tracks whether `scrollRef` is at (or within a threshold of) its bottom, so a
// scroll-to-bottom affordance can show only when the user has scrolled up. Recomputed on
// scroll and whenever `contentVersion` changes (streaming grows the content, which can move
// the bottom away without a scroll event). Nothing here scrolls the view on its own.
const useScrollToBottom = (
  scrollRef: RefObject<HTMLElement | null>,
  contentVersion: unknown,
): ScrollToBottom => {
  const [isAtBottom, setIsAtBottom] = useState(true);

  const measure = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setIsAtBottom(distance <= AT_BOTTOM_THRESHOLD);
  }, [scrollRef]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.addEventListener("scroll", measure, { passive: true });
    measure();
    return () => el.removeEventListener("scroll", measure);
  }, [scrollRef, measure]);

  useEffect(() => {
    measure();
  }, [contentVersion, measure]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [scrollRef]);

  return { isAtBottom, scrollToBottom };
};

export default useScrollToBottom;
