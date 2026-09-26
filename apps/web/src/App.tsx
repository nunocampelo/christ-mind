import type { AgentStreamEvent } from "@/api/agentApi";
import ChatLanding from "@/components/chat/ChatLanding";
import Composer from "@/components/chat/Composer";
import Transcript from "@/components/chat/Transcript";
import useA2AChat from "@/hooks/useA2AChat";

interface AppProps {
  streamFn?: (
    message: string,
    contextId: string,
    signal?: AbortSignal,
  ) => AsyncGenerator<AgentStreamEvent, void, void>;
}

/** PR 2: typing a situation posts it to the agent; the streamed markdown answer and
    the cited-vs-inferred structure render in the transcript. The landing screen shows
    until the first turn. `streamFn` is the test seam (default: the real transport). */
const App = ({ streamFn }: AppProps = {}) => {
  const {
    turns,
    busy,
    error,
    draft,
    setDraft,
    handleSubmit,
    handleInputKeyDown,
    handleCancel,
  } = useA2AChat({ streamFn });

  return (
    <div className="flex h-dvh flex-col bg-background">
      <main className="flex flex-1 flex-col overflow-y-auto">
        {turns.length === 0 ? (
          <ChatLanding />
        ) : (
          <Transcript turns={turns} busy={busy} />
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
          disabled={busy}
          busy={busy}
          onChange={setDraft}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          onKeyDown={handleInputKeyDown}
        />
      </div>
    </div>
  );
};

export default App;
