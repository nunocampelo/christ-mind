import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConversationSummary } from "@/api/conversationsApi";
import useConversations from "@/hooks/useConversations";

const summary = (id: string): ConversationSummary => ({
  conversation_id: id,
  summary: id,
  created_at: "2026-01-01T00:00:00",
  updated_at: "2026-01-01T00:00:00",
});

describe("useConversations", () => {
  it("fetches the list on mount", async () => {
    const listFn = vi.fn(async () => [summary("a"), summary("b")]);
    const { result } = renderHook(() => useConversations({ listFn }));

    await waitFor(() =>
      expect(result.current.conversations.map((c) => c.conversation_id)).toEqual([
        "a",
        "b",
      ]),
    );
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(listFn).toHaveBeenCalledOnce();
  });

  it("refetches on demand", async () => {
    let batch = [summary("a")];
    const listFn = vi.fn(async () => batch);
    const { result } = renderHook(() => useConversations({ listFn }));

    await waitFor(() => expect(result.current.conversations).toHaveLength(1));

    batch = [summary("a"), summary("c")];
    await act(async () => {
      await result.current.refetch();
    });
    expect(result.current.conversations.map((c) => c.conversation_id)).toEqual([
      "a",
      "c",
    ]);
  });

  it("surfaces an error when the fetch fails", async () => {
    const listFn = vi.fn(async () => {
      throw new Error("network");
    });
    const { result } = renderHook(() => useConversations({ listFn }));

    await waitFor(() =>
      expect(result.current.error).toBe("Could not load conversations"),
    );
    expect(result.current.conversations).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
});
