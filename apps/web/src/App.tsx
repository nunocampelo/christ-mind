import { useCallback, useRef } from "react";
import type { AgentStreamEvent } from "@/api/agentApi";
import ChatLanding from "@/components/chat/ChatLanding";
import Composer from "@/components/chat/Composer";
import ScrollToBottomButton from "@/components/chat/ScrollToBottomButton";
import Transcript from "@/components/chat/Transcript";
import useA2AChat from "@/hooks/useA2AChat";
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
}

/** PR 2: typing a situation posts it to the agent; the streamed markdown answer and
    the cited-vs-inferred structure render in the transcript. The landing screen shows
    until the first turn. `streamFn`/`recoverFn` are the test seams (default: the real
    transport). */
const App = ({ streamFn, recoverFn }: AppProps = {}) => {
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
  } = useA2AChat({ streamFn, recoverFn, onSend });

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
      <div className="sticky bottom-0 border-t border-border bg-background/80 backdrop-blur">
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

export default App;
