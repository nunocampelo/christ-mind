/// <reference types="vitest/config" />
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const a2aPort = process.env.VITE_A2A_PORT || "8765";
const a2aTarget = `http://127.0.0.1:${a2aPort}`;

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
  // VITE_A2A_PORT overrides the backend port (default 8765) so a second Vite instance
  // can proxy to a second backend (e.g. the eval DB on :8767).
  server: {
    port: 5273,
    strictPort: true,
    proxy: {
      "/a2a": { target: a2aTarget, changeOrigin: true },
      "/.well-known": { target: a2aTarget, changeOrigin: true },
      "/conversations": { target: a2aTarget, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
