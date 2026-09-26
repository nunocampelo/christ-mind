const DARK_QUERY = "(prefers-color-scheme: dark)";

function applyTheme(prefersDark: boolean): void {
  document.documentElement.classList.toggle("dark", prefersDark);
}

export function syncThemeWithOS(): () => void {
  const media = window.matchMedia(DARK_QUERY);
  applyTheme(media.matches);

  const onChange = (event: MediaQueryListEvent) => applyTheme(event.matches);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
