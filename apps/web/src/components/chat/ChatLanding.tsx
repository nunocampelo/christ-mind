import "@/components/chat/chat.css";

/** Full-screen empty state: greeting + gradient-clipped title, centered.
    No prompt cards (deferred until sending works, per the plan). */
const ChatLanding = () => (
  <div className="relative flex flex-1 flex-col items-center justify-center px-4 text-center">
    <div className="landing-glow" aria-hidden="true" />
    <p className="mb-3 text-sm font-medium uppercase tracking-widest text-muted-foreground">
      A Course in Miracles
    </p>
    <h1 className="landing-title text-4xl font-semibold sm:text-5xl">
      Mind of Christ
    </h1>
    <p className="mt-4 max-w-md text-base text-muted-foreground">
      Describe a situation, and receive guidance grounded in what the Course says —
      kept distinct from what follows from it.
    </p>
  </div>
);

export default ChatLanding;
