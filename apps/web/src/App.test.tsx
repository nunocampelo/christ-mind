import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "@/App";

describe("PR 1 — the chat app renders", () => {
  it("shows the greeting and title on the landing screen", () => {
    render(<App />);
    expect(
      screen.getByRole("heading", { name: "Mind of Christ" }),
    ).toBeInTheDocument();
    expect(screen.getByText("A Course in Miracles")).toBeInTheDocument();
  });

  it("shows a composer with the situation placeholder", () => {
    render(<App />);
    const input = screen.getByTestId("composer-input");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder", "Describe a situation…");
  });

  it("keeps the send button disabled (nothing sends yet)", () => {
    render(<App />);
    expect(screen.getByTestId("composer-send")).toBeDisabled();
  });

  it("keeps the input inert (disabled) in the shell-only slice", () => {
    render(<App />);
    expect(screen.getByTestId("composer-input")).toBeDisabled();
  });
});
