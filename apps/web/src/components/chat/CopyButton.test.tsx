import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CopyButton from "@/components/chat/CopyButton";

describe("CopyButton", () => {
  it("writes the message text to the clipboard and confirms", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<CopyButton text="Forgiveness undoes it." />);
    const button = screen.getByTestId("copy-button");
    expect(button).toHaveAttribute("aria-label", "Copy message");

    fireEvent.click(button);

    expect(writeText).toHaveBeenCalledWith("Forgiveness undoes it.");
    await waitFor(() =>
      expect(button).toHaveAttribute("aria-label", "Copied"),
    );
  });
});
