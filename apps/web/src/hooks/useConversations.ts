import { useCallback, useEffect, useState } from "react";
import {
  listConversations as defaultListConversations,
  type ConversationSummary,
} from "@/api/conversationsApi";

type ListFn = () => Promise<ConversationSummary[]>;

interface UseConversationsOptions {
  listFn?: ListFn;
}

/** Sidebar list state. `listFn` is the DI seam (default: the real /conversations fetch).
    Callers `refetch()` after a new conversation's first turn (and rename/delete in PR E). */
const useConversations = ({
  listFn = defaultListConversations,
}: UseConversationsOptions = {}) => {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      setConversations(await listFn());
      setError(null);
    } catch {
      setError("Could not load conversations");
    } finally {
      setLoading(false);
    }
  }, [listFn]);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  return { conversations, loading, error, refetch };
};

export default useConversations;
