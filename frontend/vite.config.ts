import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Single-page app, no server-side rendering. The browser only talks to this dev server;
// /api is proxied to the FastAPI backend, so no API key and no backend URL reach browser code.
const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  preview: {
    port: 5173,
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
});
