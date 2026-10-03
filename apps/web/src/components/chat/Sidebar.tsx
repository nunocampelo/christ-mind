import { useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/cn";
import type { ConversationSummary } from "@/api/conversationsApi";

interface SidebarProps {
  conversations: ConversationSummary[];
  activeConversationId?: string;
  loading?: boolean;
  onRename?: (id: string, summary: string) => void;
  onDelete?: (id: string) => void;
}

const UNTITLED = "New conversation";
const ENTER = "Enter";
const ESCAPE = "Escape";

const iconProps = {
  viewBox: "0 0 24 24",
  className: "h-3.5 w-3.5",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

const ComposeIcon = () => (
  <svg {...iconProps} className="h-4 w-4">
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

const PencilIcon = () => (
  <svg {...iconProps}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </svg>
);

const TrashIcon = () => (
  <svg {...iconProps}>
    <path d="M3 6h18" />
    <path d="M8 6V4h8v2" />
    <path d="M6 6l1 14h10l1-14" />
  </svg>
);

const CheckIcon = () => (
  <svg {...iconProps}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

const XIcon = () => (
  <svg {...iconProps}>
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </svg>
);

const GraphIcon = () => (
  <svg {...iconProps} className="h-4 w-4">
    <circle cx="5" cy="6" r="2.5" />
    <circle cx="18" cy="7" r="2.5" />
    <circle cx="12" cy="18" r="2.5" />
    <path d="M7.3 7.1 10 16M15.9 8.6 13 16M7 6.4h8.5" />
  </svg>
);

const GHOST_ICON_BTN =
  "inline-flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95";

interface RowProps {
  conversation: ConversationSummary;
  active: boolean;
  onRename?: (id: string, summary: string) => void;
  onDelete?: (id: string) => void;
}

const ConversationRow = ({
  conversation,
  active,
  onRename,
  onDelete,
}: RowProps) => {
  const id = conversation.conversation_id;
  const title = conversation.summary ?? UNTITLED;
  const [mode, setMode] = useState<"idle" | "editing" | "confirming">("idle");
  const [draft, setDraft] = useState(title);

  const commitRename = () => {
    const next = draft.trim();
    if (next && next !== title) onRename?.(id, next);
    setMode("idle");
  };

  const onInputKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>) => {
    if (event.key === ENTER) {
      event.preventDefault();
      commitRename();
    } else if (event.key === ESCAPE) {
      event.preventDefault();
      setMode("idle");
      setDraft(title);
    }
  };

  if (mode === "editing") {
    return (
      <div className="flex items-center rounded-[var(--radius-app)] bg-muted px-2 py-1">
        <input
          data-testid="rename-input"
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onInputKeyDown}
          onBlur={commitRename}
          className="min-w-0 flex-1 bg-transparent px-1 text-sm text-foreground focus:outline-none"
        />
      </div>
    );
  }

  return (
    <div
      data-testid="conversation-item"
      data-active={active}
      className={cn(
        "group flex items-center rounded-[var(--radius-app)] pr-1 text-sm",
        active
          ? "bg-muted font-medium text-foreground"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      <Link
        to={`/c/${id}`}
        data-testid="conversation-link"
        title={title}
        className="min-w-0 flex-1 truncate px-3 py-2 focus-visible:outline-none"
      >
        {title}
      </Link>

      {mode === "confirming" ? (
        <div className="flex shrink-0 items-center">
          <button
            type="button"
            data-testid="confirm-delete"
            aria-label="Confirm delete"
            onClick={() => onDelete?.(id)}
            className={GHOST_ICON_BTN}
          >
            <CheckIcon />
          </button>
          <button
            type="button"
            data-testid="cancel-delete"
            aria-label="Cancel delete"
            onClick={() => setMode("idle")}
            className={GHOST_ICON_BTN}
          >
            <XIcon />
          </button>
        </div>
      ) : (
        <div className="flex shrink-0 items-center opacity-0 focus-within:opacity-100 group-hover:opacity-100">
          <button
            type="button"
            data-testid="rename-conversation"
            aria-label="Rename conversation"
            onClick={() => {
              setDraft(title);
              setMode("editing");
            }}
            className={GHOST_ICON_BTN}
          >
            <PencilIcon />
          </button>
          <button
            type="button"
            data-testid="delete-conversation"
            aria-label="Delete conversation"
            onClick={() => setMode("confirming")}
            className={GHOST_ICON_BTN}
          >
            <TrashIcon />
          </button>
        </div>
      )}
    </div>
  );
};

const Sidebar = ({
  conversations,
  activeConversationId,
  loading,
  onRename,
  onDelete,
}: SidebarProps) => {
  const onGraph = useLocation().pathname === "/graph";
  return (
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
      Explore
    </p>
    <div className="px-2 pb-3">
      <Link
        to="/graph"
        data-testid="graph-link"
        data-active={onGraph}
        aria-current={onGraph ? "page" : undefined}
        className={cn(
          "flex items-center gap-2 rounded-[var(--radius-app)] px-3 py-2 text-sm",
          onGraph
            ? "bg-muted font-medium text-foreground"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
        )}
      >
        <GraphIcon />
        Course graph
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
        conversations.map((conversation) => (
          <ConversationRow
            key={conversation.conversation_id}
            conversation={conversation}
            active={conversation.conversation_id === activeConversationId}
            onRename={onRename}
            onDelete={onDelete}
          />
        ))
      )}
    </nav>
  </aside>
  );
};

export default Sidebar;
