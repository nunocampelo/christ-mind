import "@testing-library/jest-dom/vitest";

// jsdom has no Element.scrollTo; the scroll hooks call it. Layout geometry is all 0 in
// jsdom, so this no-op stub just lets components that scroll render without throwing (tests
// that assert scroll behavior stub scrollTo with a spy of their own).
Element.prototype.scrollTo ??= () => {};
