import { useState } from "react";
import ChatLanding from "@/components/chat/ChatLanding";
import Composer from "@/components/chat/Composer";

/** PR 1: full-viewport shell — landing screen above, sticky composer below.
    Input is inert (nothing sends yet); PR 2 replaces the local draft state with
    useA2AChat and renders a transcript in place of the landing screen. */
const App = () => {
  const [draft, setDraft] = useState("");

  return (
    <div className="flex h-dvh flex-col bg-background">
      <main className="flex flex-1 flex-col overflow-y-auto">
        <ChatLanding />
      </main>
      <div className="sticky bottom-0 border-t border-border bg-background/80 backdrop-blur">
        <Composer
          value={draft}
          disabled
          onChange={setDraft}
          onSubmit={() => {}}
        />
      </div>
    </div>
  );
};

export default App;
