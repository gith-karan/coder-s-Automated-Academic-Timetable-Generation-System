import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import type { Plugin } from "vite";

/** Production builds carry a strict Content-Security-Policy (dev needs inline scripts for hot reload). */
const CSP = [
  "default-src 'self'", "script-src 'self'", "style-src 'self' 'unsafe-inline'", "img-src 'self' data: blob:",
  "font-src 'self' data:", "connect-src 'self'", "object-src 'none'", "base-uri 'self'", "form-action 'self'",
].join("; ");
const cspMeta = (): Plugin => ({
  name: "csp-meta",
  apply: "build",
  transformIndexHtml: (html) => html.replace("<head>", `<head>
    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`),
});

export default defineConfig({
  plugins: [react(), tailwindcss(), cspMeta()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    strictPort: true,
    // Same-origin API in development: cookies stay SameSite=Strict and no CORS is needed.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: {
    sourcemap: false,
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks: { react: ["react", "react-dom", "react-router-dom"], query: ["@tanstack/react-query"] },
      },
    },
  },
});
