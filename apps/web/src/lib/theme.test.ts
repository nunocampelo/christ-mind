import { afterEach, describe, expect, it, vi } from "vitest";
import { syncThemeWithOS } from "@/lib/theme";

type ChangeListener = (event: MediaQueryListEvent) => void;

function stubMatchMedia(initialMatches: boolean) {
  const listeners = new Set<ChangeListener>();
  const media = {
    matches: initialMatches,
    addEventListener: vi.fn((_: string, cb: ChangeListener) => {
      listeners.add(cb);
    }),
    removeEventListener: vi.fn((_: string, cb: ChangeListener) => {
      listeners.delete(cb);
    }),
  };
  window.matchMedia = vi.fn(() => media) as unknown as typeof window.matchMedia;

  const emit = (matches: boolean) => {
    media.matches = matches;
    for (const cb of listeners) cb({ matches } as MediaQueryListEvent);
  };
  return { media, emit };
}

afterEach(() => {
  document.documentElement.classList.remove("dark");
});

describe("syncThemeWithOS", () => {
  it("adds the dark class when the OS prefers dark", () => {
    stubMatchMedia(true);
    syncThemeWithOS();
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("removes the dark class when the OS prefers light", () => {
    document.documentElement.classList.add("dark");
    stubMatchMedia(false);
    syncThemeWithOS();
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("flips the class when the OS preference changes", () => {
    const { emit } = stubMatchMedia(false);
    syncThemeWithOS();
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    emit(true);
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    emit(false);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("unsubscribes the listener when the returned cleanup runs", () => {
    const { media } = stubMatchMedia(true);
    const cleanup = syncThemeWithOS();
    cleanup();
    expect(media.removeEventListener).toHaveBeenCalledOnce();
  });
});
