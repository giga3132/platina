import { defineConfig } from "vite";

// The backend runs on :8000 (uvicorn); /api/* is proxied to it.
export default defineConfig({
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
