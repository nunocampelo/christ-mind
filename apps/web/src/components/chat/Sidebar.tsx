import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";
import type { ConversationSummary } from "@/api/conversationsApi";

interface SidebarProps {
  conversations: ConversationSummary[];
  activeConversationId?: string;
  loading?: boolean;
}

const UNTITLED = "New conversation";

const ComposeIcon = () => (
  <svg
    viewBox="0 0 24 24"
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

const Sidebar = ({
  conversations,
  activeConversationId,
  loading,
}: SidebarProps) => (
  <aside className="flex h-dvh w-64 shrink-0 flex-col border-r border-border bg-muted/30">
    <div className="p-3">
      <Link
        to="/"
        data-testid="new-chat"
        className="flex items-center gap-2 rounded-[var(--radius-app)] px-3 py-2 text-sm font-medium text-foreground hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ComposeIcon />
        New chat
      </Link>
    </div>

    <p className="px-4 pb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
      Recents
    </p>
    <nav
      data-testid="conversation-list"
      className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {loading && conversations.length === 0 ? (
        <p className="px-3 py-2 text-sm text-muted-foreground">Loading…</p>
      ) : conversations.length === 0 ? (
        <p className="px-3 py-2 text-sm text-muted-foreground">No conversations yet</p>
      ) : (
        conversations.map((conversation) => {
          const active = conversation.conversation_id === activeConversationId;
          return (
            <Link
              key={conversation.conversation_id}
              to={`/c/${conversation.conversation_id}`}
              data-testid="conversation-item"
              data-active={active}
              title={conversation.summary ?? UNTITLED}
              className={cn(
                "truncate rounded-[var(--radius-app)] px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "bg-muted font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {conversation.summary ?? UNTITLED}
            </Link>
          );
        })
      )}
    </nav>
  </aside>
);

export default Sidebar;
