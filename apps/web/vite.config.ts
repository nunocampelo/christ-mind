/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  // The A2A client reads the agent card from /.well-known first, then dials the
  // absolute endpoint URL the card advertises, so BOTH paths must be proxied. Run the
  // backend with AGENT_PUBLIC_URL=http://localhost:5273 so the card advertises this
  // origin — keeping both the card fetch and streaming same-origin (no CORS).
  // /conversations is the REST history read surface (same-origin fetch from the app).
  // strictPort so a taken port fails loudly instead of drifting to 5274 — a silent
  // drift makes the card (fixed on 5273) dial a different app on 5273 and 404.
  server: {
    port: 5273,
    strictPort: true,
    proxy: {
      "/a2a": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/.well-known": { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/conversations": { target: "http://127.0.0.1:8765", changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
