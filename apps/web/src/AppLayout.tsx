import { useCallback } from "react";
import { Outlet, useNavigate, useOutletContext, useParams } from "react-router-dom";
import {
  deleteConversation as defaultDeleteConversation,
  listConversations as defaultListConversations,
  renameConversation as defaultRenameConversation,
  type ConversationSummary,
} from "@/api/conversationsApi";
import Sidebar from "@/components/chat/Sidebar";
import useConversations from "@/hooks/useConversations";

// The shell: owns the one `useConversations` fetch and renders the persistent sidebar for
// every route (chat and /graph), with the chat column / graph page swapped in via <Outlet>.
// The graph route reads none of this — it just rides along so the sidebar stays visible —
// which is why the fetch lives here, once, instead of inside the chat (plan 0030).
export interface ChatOutletContext {
  conversations: ConversationSummary[];
  refetch: () => Promise<void>;
}

export const useChatContext = (): ChatOutletContext =>
  useOutletContext<ChatOutletContext>();

interface AppLayoutProps {
  listConversations?: () => Promise<ConversationSummary[]>;
  renameConversation?: (id: string, summary: string) => Promise<void>;
  deleteConversation?: (id: string) => Promise<void>;
}

const AppLayout = ({
  listConversations,
  renameConversation,
  deleteConversation,
}: AppLayoutProps = {}) => {
  const rename = renameConversation ?? defaultRenameConversation;
  const remove = deleteConversation ?? defaultDeleteConversation;
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { conversations, loading, refetch } = useConversations({
    listFn: listConversations ?? defaultListConversations,
  });

  const onRename = useCallback(
    (id: string, summary: string) => {
      void rename(id, summary).then(refetch);
    },
    [rename, refetch],
  );

  const onDelete = useCallback(
    (id: string) => {
      void remove(id).then(() => {
        if (id === conversationId) navigate("/", { replace: true });
        return refetch();
      });
    },
    [remove, refetch, conversationId, navigate],
  );

  return (
    <div className="flex h-dvh">
      <Sidebar
        conversations={conversations}
        activeConversationId={conversationId}
        loading={loading}
        onRename={onRename}
        onDelete={onDelete}
      />
      <Outlet context={{ conversations, refetch } satisfies ChatOutletContext} />
    </div>
  );
};

export default AppLayout;
