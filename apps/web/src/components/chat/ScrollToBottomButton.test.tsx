import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import ScrollToBottomButton from "@/components/chat/ScrollToBottomButton";

describe("ScrollToBottomButton", () => {
  it("is interactive and opaque when visible", () => {
    render(<ScrollToBottomButton visible={true} onClick={() => {}} />);
    const btn = screen.getByTestId("scroll-to-bottom");
    expect(btn).toHaveClass("opacity-100");
    expect(btn).not.toHaveClass("pointer-events-none");
    expect(btn).toHaveAttribute("aria-hidden", "false");
  });

  it("is hidden and non-interactive when not visible", () => {
    render(<ScrollToBottomButton visible={false} onClick={() => {}} />);
    const btn = screen.getByTestId("scroll-to-bottom");
    expect(btn).toHaveClass("opacity-0");
    expect(btn).toHaveClass("pointer-events-none");
    expect(btn).toHaveAttribute("aria-hidden", "true");
    expect(btn).toHaveAttribute("tabindex", "-1");
  });

  it("calls onClick when pressed", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<ScrollToBottomButton visible={true} onClick={onClick} />);
    await user.click(screen.getByTestId("scroll-to-bottom"));
    expect(onClick).toHaveBeenCalledOnce();
  });
});
