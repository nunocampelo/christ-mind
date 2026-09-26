import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

interface ScrollAnchor {
  scrollRef: React.RefObject<HTMLDivElement | null>;
  spacerHeight: number;
  anchorOnSend: () => void;
}

// Anchors the newest user turn ~1/3 down the viewport on send (ChatGPT-style): a tail
// spacer reserves just enough room — up to 2/3 of a viewport, minus whatever already
// follows the turn — so the answer streams into the space below while the previous answer
// stays visible above. Because the reserve targets 2/3 (not a full screen) and subtracts
// content already there, a short exchange whose content already exceeds 2/3 reserves 0 —
// no transient overflow, no scrollbar flicker. Ported from gcm's proven exp_agent_chat.
// `active` is the streaming flag; `contentVersion` changes as tokens arrive so the spacer
// recomputes synchronously (pre-paint) in step with the growing reply — no lag frame where
// content has grown but the spacer hasn't shrunk yet, which is what flashed the scrollbar.
const useScrollAnchor = (active: boolean, contentVersion: unknown): ScrollAnchor => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [spacerHeight, setSpacerHeight] = useState(0);

  const recomputeSpacer = useCallback(() => {
    const container = scrollRef.current;
    if (!container) {
      setSpacerHeight(0);
      return;
    }
    const userTurns = container.querySelectorAll<HTMLElement>("[data-role='user']");
    const userTurn = userTurns[userTurns.length - 1];
    const turnNodes = container.querySelectorAll<HTMLElement>("[data-turn]");
    const lastTurn = turnNodes[turnNodes.length - 1];
    if (!userTurn || !lastTurn) {
      setSpacerHeight(0);
      return;
    }
    const userTop = userTurn.getBoundingClientRect().top;
    const contentBottom = lastTurn.getBoundingClientRect().bottom;
    const contentBelow = contentBottom - userTop;
    const needed = Math.round((container.clientHeight * 2) / 3) - contentBelow;
    setSpacerHeight(Math.max(0, needed));
  }, []);

  const anchorNewestUserTurn = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;
    const nodes = container.querySelectorAll<HTMLElement>("[data-role='user']");
    const target = nodes[nodes.length - 1];
    if (!target) return;
    const containerTop = container.getBoundingClientRect().top;
    const bubbleTop = target.getBoundingClientRect().top;
    const offsetWithin = container.scrollTop + (bubbleTop - containerTop);
    const top = offsetWithin - Math.round(container.clientHeight / 3);
    container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }, []);

  const anchorOnSend = useCallback(() => {
    requestAnimationFrame(() => {
      recomputeSpacer();
      requestAnimationFrame(anchorNewestUserTurn);
    });
  }, [anchorNewestUserTurn, recomputeSpacer]);

  // Shrink the spacer in the same commit the reply grows, before the browser paints, so a
  // new token never overshoots the viewport for a frame. The ResizeObserver below is the
  // backstop for growth React can't see (images, async layout, viewport resize).
  useLayoutEffect(() => {
    if (!active) return;
    recomputeSpacer();
  }, [active, contentVersion, recomputeSpacer]);

  useEffect(() => {
    if (!active) {
      setSpacerHeight(0);
      return;
    }
    const container = scrollRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => recomputeSpacer());
    observer.observe(container);
    return () => observer.disconnect();
  }, [active, recomputeSpacer]);

  return { scrollRef, spacerHeight, anchorOnSend };
};

export default useScrollAnchor;
