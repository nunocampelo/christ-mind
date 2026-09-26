import "@testing-library/jest-dom/vitest";

// jsdom implements neither ResizeObserver nor Element.scrollTo; useScrollAnchor uses both.
// Layout-dependent behavior can't be exercised in jsdom (offsetTop/scrollHeight are 0), so
// these no-op stubs just let components that mount the hook render without throwing.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;
Element.prototype.scrollTo ??= () => {};
