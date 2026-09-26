import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import useScrollAnchor from "@/hooks/useScrollAnchor";

const flushFrames = () =>
  act(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );

const observers: { disconnect: ReturnType<typeof vi.fn> }[] = [];

class ObserverSpy {
  disconnect = vi.fn();
  observe() {}
  unobserve() {}
  constructor() {
    observers.push(this);
  }
}

// jsdom reports 0 for layout, so stub getBoundingClientRect on the nodes useScrollAnchor
// queries. `userBottom` models how far the last turn's content reaches below the user
// turn's top; when it already exceeds 2/3 of the viewport the spacer must be 0.
const stubRect = (el: Element, rect: Partial<DOMRect>) => {
  el.getBoundingClientRect = () => ({ top: 0, bottom: 0, ...rect }) as DOMRect;
};
const stubClientHeight = (el: Element, value: number) =>
  Object.defineProperty(el, "clientHeight", { configurable: true, value });

const Harness = ({
  active,
  userTop,
  contentBottom,
  viewport,
}: {
  active: boolean;
  userTop: number;
  contentBottom: number;
  viewport: number;
}) => {
  const { scrollRef, spacerHeight, anchorOnSend } = useScrollAnchor(
    active,
    contentBottom,
  );
  return (
    <div
      ref={(el) => {
        if (el) {
          stubClientHeight(el, viewport);
          stubRect(el, { top: 0 });
        }
        scrollRef.current = el;
      }}
    >
      <div
        data-turn
        data-role="user"
        ref={(el) => {
          if (el) stubRect(el, { top: userTop, bottom: userTop + 40 });
        }}
      >
        user
      </div>
      <div
        data-turn
        data-role="agent"
        ref={(el) => {
          if (el) stubRect(el, { top: userTop + 40, bottom: contentBottom });
        }}
      >
        agent
      </div>
      <div data-testid="spacer" style={{ height: spacerHeight }} />
      <button data-testid="go" onClick={anchorOnSend}>
        send
      </button>
    </div>
  );
};

describe("useScrollAnchor", () => {
  let scrollTo: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    observers.length = 0;
    scrollTo = vi.fn();
    Element.prototype.scrollTo = scrollTo;
    globalThis.ResizeObserver = ObserverSpy as unknown as typeof ResizeObserver;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reserves no spacer when content already fills 2/3 of the viewport (no flicker)", async () => {
    // viewport 900 → 2/3 = 600; content below the user top = 700 > 600 → needed < 0 → 0.
    const { getByTestId } = render(
      <Harness active={true} userTop={0} contentBottom={700} viewport={900} />,
    );
    getByTestId("go").click();
    await flushFrames();
    expect(getByTestId("spacer").style.height).toBe("0px");
  });

  it("reserves the 2/3 deficit when little follows the newest turn", async () => {
    // viewport 900 → 2/3 = 600; content below = 90 → needed = 510.
    const { getByTestId } = render(
      <Harness active={true} userTop={0} contentBottom={90} viewport={900} />,
    );
    getByTestId("go").click();
    await flushFrames();
    expect(getByTestId("spacer").style.height).toBe("510px");
  });

  it("scrolls to park the newest user turn ~1/3 down the viewport", async () => {
    const { getByTestId } = render(
      <Harness active={true} userTop={600} contentBottom={700} viewport={900} />,
    );
    getByTestId("go").click();
    await flushFrames();
    // offsetWithin = scrollTop(0) + (600 - 0) = 600; top = 600 - round(900/3) = 300.
    expect(scrollTo).toHaveBeenCalledWith({ top: 300, behavior: "smooth" });
  });

  it("observes while active and disconnects when it goes idle", () => {
    const { rerender } = render(
      <Harness active={true} userTop={0} contentBottom={90} viewport={900} />,
    );
    expect(observers).toHaveLength(1);
    rerender(
      <Harness active={false} userTop={0} contentBottom={90} viewport={900} />,
    );
    expect(observers[0].disconnect).toHaveBeenCalled();
  });

  it("collapses the spacer to zero when idle", () => {
    const { getByTestId } = render(
      <Harness active={false} userTop={0} contentBottom={90} viewport={900} />,
    );
    expect(getByTestId("spacer").style.height).toBe("0px");
  });
});
