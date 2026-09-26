import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentStreamEvent } from "@/api/agentApi";
import {
  getConversation as defaultGetConversation,
  turnsFromConversation,
  type ConversationDetail,
} from "@/api/conversationsApi";
import ChatLanding from "@/components/chat/ChatLanding";
import Composer from "@/components/chat/Composer";
import ScrollToBottomButton from "@/components/chat/ScrollToBottomButton";
import Transcript from "@/components/chat/Transcript";
import useA2AChat, { type Turn } from "@/hooks/useA2AChat";
import useScrollAnchor from "@/hooks/useScrollAnchor";
import useScrollToBottom from "@/hooks/useScrollToBottom";

const CONTEXT_KEY = "christ-mind.agent.contextId";

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
}

interface ChatProps extends AppProps {
  initialContextId: string;
  initialTurns: Turn[];
}

/** The chat itself, mounted only once rehydration has resolved so `useA2AChat` seeds from
    the restored conversation. Split from `App` to keep the hook's seeds ready before its
    first render. */
const Chat = ({
  streamFn,
  recoverFn,
  initialContextId,
  initialTurns,
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
  });

  const { scrollRef, spacerHeight, anchorOnSend } = useScrollAnchor(busy);
  anchorRef.current = anchorOnSend;

  const streamingText = turns.length ? turns[turns.length - 1].text : "";
  const { isAtBottom, scrollToBottom } = useScrollToBottom(
    scrollRef,
    `${streamingText.length}:${spacerHeight}`,
  );

  return (
    <div className="flex h-dvh flex-col bg-background">
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
      <div className="sticky bottom-0 border-t border-border bg-background/80 pt-3 backdrop-blur">
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

/** Rehydrate the stored conversation before mounting the chat: read the saved contextId,
    fetch its history, rebuild the turns. A missing/stale id (or none) starts fresh.
    `loadConversation` is the test seam (default: the real /conversations fetch). */
type Seeds = { contextId: string; turns: Turn[] };

const App = ({ streamFn, recoverFn, loadConversation }: AppProps = {}) => {
  const load = loadConversation ?? defaultGetConversation;
  const storedId = sessionStorage.getItem(CONTEXT_KEY) ?? "";
  // No stored conversation → seed empty synchronously, so there's no loading flash and the
  // fresh-chat path is unchanged. Only a stored id defers the mount to fetch its history.
  const [seeds, setSeeds] = useState<Seeds | null>(
    storedId ? null : { contextId: "", turns: [] },
  );

  useEffect(() => {
    if (!storedId) return;
    let active = true;

    const rehydrate = async (): Promise<Seeds> => {
      try {
        const detail = await load(storedId);
        if (!detail) {
          sessionStorage.removeItem(CONTEXT_KEY);
          return { contextId: "", turns: [] };
        }
        return { contextId: storedId, turns: turnsFromConversation(detail) };
      } catch {
        // A load failure shouldn't block the chat — start fresh, keep the stored id.
        return { contextId: storedId, turns: [] };
      }
    };

    void rehydrate().then((result) => {
      if (active) setSeeds(result);
    });
    return () => {
      active = false;
    };
  }, [load, storedId]);

  if (seeds === null) return <div className="h-dvh bg-background" />;

  return (
    <Chat
      streamFn={streamFn}
      recoverFn={recoverFn}
      initialContextId={seeds.contextId}
      initialTurns={seeds.turns}
    />
  );
};

export default App;
