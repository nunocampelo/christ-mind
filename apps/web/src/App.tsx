import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { AgentStreamEvent } from "@/api/agentApi";
import {
  deleteConversation as defaultDeleteConversation,
  getConversation as defaultGetConversation,
  listConversations as defaultListConversations,
  renameConversation as defaultRenameConversation,
  turnsFromConversation,
  type ConversationDetail,
  type ConversationSummary,
} from "@/api/conversationsApi";
import ChatLanding from "@/components/chat/ChatLanding";
import Composer from "@/components/chat/Composer";
import ScrollToBottomButton from "@/components/chat/ScrollToBottomButton";
import Sidebar from "@/components/chat/Sidebar";
import Transcript from "@/components/chat/Transcript";
import useA2AChat, { type Turn } from "@/hooks/useA2AChat";
import useConversations from "@/hooks/useConversations";
import useScrollAnchor from "@/hooks/useScrollAnchor";
import useScrollToBottom from "@/hooks/useScrollToBottom";

interface AppProps {
  streamFn?: (
    message: string,
    contextId: string,
    signal?: AbortSignal,
  ) => AsyncGenerator<AgentStreamEvent, void, void>;
  recoverFn?: (
    taskId: string,
    textSoFar: string,
  ) => AsyncGenerator<AgentStreamEvent, void, void>;
  loadConversation?: (id: string) => Promise<ConversationDetail | null>;
  listConversations?: () => Promise<ConversationSummary[]>;
  renameConversation?: (id: string, summary: string) => Promise<void>;
  deleteConversation?: (id: string) => Promise<void>;
}

interface ChatProps {
  streamFn?: AppProps["streamFn"];
  recoverFn?: AppProps["recoverFn"];
  initialContextId: string;
  initialTurns: Turn[];
  onConversationId: (id: string) => void;
}

/** The chat column, keyed on the active conversation so a route change remounts it (aborting
    any in-flight stream) and reseeds from the newly resolved history. */
const Chat = ({
  streamFn,
  recoverFn,
  initialContextId,
  initialTurns,
  onConversationId,
}: ChatProps) => {
  const anchorRef = useRef<() => void>(() => {});
  const onSend = useCallback(() => anchorRef.current(), []);
  const {
    turns,
    busy,
    error,
    draft,
    canReconnect,
    setDraft,
    handleSubmit,
    handleInputKeyDown,
    handleCancel,
    handleReconnect,
  } = useA2AChat({
    streamFn,
    recoverFn,
    onSend,
    initialContextId,
    initialTurns,
    onConversationId,
  });

  const { scrollRef, spacerHeight, anchorOnSend } = useScrollAnchor(busy);
  anchorRef.current = anchorOnSend;

  const streamingText = turns.length ? turns[turns.length - 1].text : "";
  const { isAtBottom, scrollToBottom } = useScrollToBottom(
    scrollRef,
    `${streamingText.length}:${spacerHeight}`,
    spacerHeight,
  );

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-background">
      <main
        ref={scrollRef}
        className="flex min-h-0 flex-1 flex-col overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {turns.length === 0 ? (
          <ChatLanding />
        ) : (
          <Transcript
            turns={turns}
            busy={busy}
            canReconnect={canReconnect}
            onReconnect={() => void handleReconnect()}
            spacerHeight={spacerHeight}
          />
        )}
      </main>
      <div className="sticky bottom-0 border-t border-border bg-background/80 pt-6 backdrop-blur">
        {error && (
          <div
            data-testid="error-strip"
            role="alert"
            className="mx-auto w-full max-w-2xl px-4 pt-3 text-sm text-red-500"
          >
            {error}
          </div>
        )}
        <Composer
          value={draft}
          busy={busy}
          onChange={setDraft}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          onKeyDown={handleInputKeyDown}
          overlay={
            turns.length > 0 ? (
              <ScrollToBottomButton visible={!isAtBottom} onClick={scrollToBottom} />
            ) : null
          }
        />
      </div>
    </div>
  );
};

type Seeds = { turns: Turn[] };

/** Route-driven shell: the `/c/:conversationId` param is the active conversation. App
    resolves that conversation's history into seeds, renders the sidebar, and remounts the
    keyed chat column on navigation. `loadConversation`/`listConversations`/`streamFn`/
    `recoverFn` are the test seams (defaults: the real APIs). */
const App = ({
  streamFn,
  recoverFn,
  loadConversation,
  listConversations,
  renameConversation,
  deleteConversation,
}: AppProps = {}) => {
  const load = loadConversation ?? defaultGetConversation;
  const rename = renameConversation ?? defaultRenameConversation;
  const remove = deleteConversation ?? defaultDeleteConversation;
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const { conversations, refetch } = useConversations({
    listFn: listConversations ?? defaultListConversations,
  });

  // The id a *live* chat minted for itself on its first turn. When the route catches up to
  // this id, the chat that owns it is already mounted and mid-stream — so we must NOT treat
  // the route change as navigation-to-another-conversation (which resets seeds, remounts,
  // and refetches history, tearing down the in-flight answer before it renders).
  const selfAssignedId = useRef<string | undefined>(undefined);
  const isSelfAssigned = conversationId !== undefined && conversationId === selfAssignedId.current;

  // Seeds resolve per active conversation: null while a detail fetch is in flight.
  const [seeds, setSeeds] = useState<Seeds | null>(
    conversationId ? null : { turns: [] },
  );
  // Reset seeds *during render* the moment the route changes, not in the effect: the keyed
  // Chat remounts on the new conversationId, and it must never seed from the previous
  // conversation's turns for even one render (that's the stale-transcript / no-landing bug).
  // The self-assigned transition is the exception: keep the live chat's own turns.
  const [seededFor, setSeededFor] = useState<string | undefined>(conversationId);
  if (seededFor !== conversationId && !isSelfAssigned) {
    setSeededFor(conversationId);
    setSeeds(conversationId ? null : { turns: [] });
    // Genuine navigation away from the self-assigned id: it's now a normal past
    // conversation, so a later return to it must rehydrate from history like any other.
    selfAssignedId.current = undefined;
  }

  useEffect(() => {
    if (!conversationId || isSelfAssigned) return;
    let active = true;
    void (async () => {
      try {
        const detail = await load(conversationId);
        if (!active) return;
        if (!detail) {
          navigate("/", { replace: true }); // stale/shared-bad id → fresh chat
          return;
        }
        setSeeds({ turns: turnsFromConversation(detail) });
      } catch {
        if (active) setSeeds({ turns: [] });
      }
    })();
    return () => {
      active = false;
    };
  }, [conversationId, isSelfAssigned, load, navigate]);

  const onConversationId = useCallback(
    (id: string) => {
      // A fresh chat's first turn just got its server id: route to it (replace, so Back
      // doesn't return to the blank "/") and refresh the sidebar so the new row appears.
      // Record it as self-assigned first so the route change keeps this live chat mounted
      // rather than remounting it and refetching (still-unpersisted) history.
      selfAssignedId.current = id;
      navigate(`/c/${id}`, { replace: true });
      void refetch();
    },
    [navigate, refetch],
  );

  const onRename = useCallback(
    (id: string, summary: string) => {
      void rename(id, summary).then(refetch);
    },
    [rename, refetch],
  );

  const onDelete = useCallback(
    (id: string) => {
      void remove(id).then(() => {
        // Deleting the conversation you're viewing drops you into a fresh chat.
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
        onRename={onRename}
        onDelete={onDelete}
      />
      {seeds === null ? (
        <div className="min-w-0 flex-1 bg-background" />
      ) : (
        <Chat
          key={isSelfAssigned ? "new" : (conversationId ?? "new")}
          streamFn={streamFn}
          recoverFn={recoverFn}
          initialContextId={conversationId ?? ""}
          initialTurns={seeds.turns}
          onConversationId={onConversationId}
        />
      )}
    </div>
  );
};

export default App;
