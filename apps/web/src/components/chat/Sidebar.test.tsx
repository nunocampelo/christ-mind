import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Sidebar from "@/components/chat/Sidebar";
import type { ConversationSummary } from "@/api/conversationsApi";

const summary = (
  id: string,
  title: string | null,
): ConversationSummary => ({
  conversation_id: id,
  summary: title,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
});

const renderSidebar = (
  props: Partial<Parameters<typeof Sidebar>[0]> = {},
  at = "/",
) =>
  render(
    <MemoryRouter initialEntries={[at]}>
      <Sidebar conversations={[]} {...props} />
    </MemoryRouter>,
  );

describe("Sidebar", () => {
  it("lists conversations and links each to its route", () => {
    renderSidebar({
      conversations: [summary("a", "First"), summary("b", "Second")],
    });
    const items = screen.getAllByTestId("conversation-item");
    expect(items.map((i) => i.textContent)).toEqual(["First", "Second"]);
    expect(items[0]).toHaveAttribute("href", "/c/a");
  });

  it("highlights the active conversation only", () => {
    renderSidebar({
      conversations: [summary("a", "First"), summary("b", "Second")],
      activeConversationId: "b",
    });
    const items = screen.getAllByTestId("conversation-item");
    expect(items[0]).toHaveAttribute("data-active", "false");
    expect(items[1]).toHaveAttribute("data-active", "true");
  });

  it("falls back to a placeholder label for an untitled conversation", () => {
    renderSidebar({ conversations: [summary("a", null)] });
    expect(screen.getByTestId("conversation-item")).toHaveTextContent(
      "New conversation",
    );
  });

  it("new-chat links to the root", async () => {
    const user = userEvent.setup();
    renderSidebar();
    const newChat = screen.getByTestId("new-chat");
    expect(newChat).toHaveAttribute("href", "/");
    await user.click(newChat); // no throw; navigation handled by the router
  });

  it("shows an empty state with no conversations", () => {
    renderSidebar({ conversations: [] });
    expect(screen.getByTestId("conversation-list")).toHaveTextContent(
      "No conversations yet",
    );
  });

  it("shows a loading state before the first list arrives", () => {
    renderSidebar({ conversations: [], loading: true });
    expect(screen.getByTestId("conversation-list")).toHaveTextContent("Loading…");
  });
});
