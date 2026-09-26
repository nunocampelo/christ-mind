import { useCallback, useEffect, useRef, useState } from "react";

interface ScrollAnchor {
  scrollRef: React.RefObject<HTMLDivElement | null>;
  spacerHeight: number;
  anchorOnSend: () => void;
}

// On send, reserve a tail spacer below the transcript and scroll the newest user turn to
// ~1/3 down the viewport, so the previous answer is pushed up and there's empty room below
// for the incoming reply to stream into. The spacer is what makes that scroll possible —
// without reserved space the container isn't tall enough to move the turn up. It holds
// through the stream and collapses when idle. The scrollbar is hidden (App), so the
// transient overflow the spacer creates is never seen; a jump-to-bottom button handles
// catching up. `active` is the streaming flag. Anchor math ported from gcm's exp_agent_chat.
const useScrollAnchor = (active: boolean): ScrollAnchor => {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [spacerHeight, setSpacerHeight] = useState(0);

  const recomputeSpacer = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;
    const userTurns = container.querySelectorAll<HTMLElement>("[data-role='user']");
    const userTurn = userTurns[userTurns.length - 1];
    const turnNodes = container.querySelectorAll<HTMLElement>("[data-turn]");
    const lastTurn = turnNodes[turnNodes.length - 1];
    if (!userTurn || !lastTurn) return;
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

  // Double rAF: the first waits for React to commit the new turns to the DOM, the second
  // for the browser to lay the spacer out, so the anchor scroll measures real positions.
  const anchorOnSend = useCallback(() => {
    requestAnimationFrame(() => {
      recomputeSpacer();
      requestAnimationFrame(anchorNewestUserTurn);
    });
  }, [anchorNewestUserTurn, recomputeSpacer]);

  useEffect(() => {
    if (!active) setSpacerHeight(0);
  }, [active]);

  return { scrollRef, spacerHeight, anchorOnSend };
};

export default useScrollAnchor;
