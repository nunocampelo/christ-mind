import { act, render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import useScrollToBottom from "@/hooks/useScrollToBottom";

const stub = (el: Element, geo: { scrollTop: number; scrollHeight: number; clientHeight: number }) => {
  Object.defineProperty(el, "scrollTop", { configurable: true, value: geo.scrollTop });
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: geo.scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: geo.clientHeight });
};

let flag: boolean | null = null;

const Harness = ({
  geo,
  version,
}: {
  geo: { scrollTop: number; scrollHeight: number; clientHeight: number };
  version: unknown;
}) => {
  const ref = useRef<HTMLDivElement | null>(null);
  const { isAtBottom, scrollToBottom } = useScrollToBottom(ref, version);
  flag = isAtBottom;
  return (
    <div
      ref={(el) => {
        if (el) stub(el, geo);
        ref.current = el;
      }}
    >
      <button data-testid="down" onClick={scrollToBottom}>
        down
      </button>
    </div>
  );
};

describe("useScrollToBottom", () => {
  let scrollTo: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    flag = null;
    scrollTo = vi.fn();
    Element.prototype.scrollTo = scrollTo;
  });

  afterEach(() => vi.restoreAllMocks());

  it("reports at-bottom when within the threshold", () => {
    render(
      <Harness geo={{ scrollTop: 990, scrollHeight: 1000, clientHeight: 10 }} version={0} />,
    );
    expect(flag).toBe(true);
  });

  it("reports not-at-bottom when scrolled up", () => {
    render(
      <Harness geo={{ scrollTop: 100, scrollHeight: 1000, clientHeight: 300 }} version={0} />,
    );
    expect(flag).toBe(false);
  });

  it("scrolls to the bottom on demand", () => {
    const { getByTestId } = render(
      <Harness geo={{ scrollTop: 0, scrollHeight: 1000, clientHeight: 300 }} version={0} />,
    );
    act(() => getByTestId("down").click());
    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: "smooth" });
  });
});
