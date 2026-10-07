import { defineConfig } from "vite";

// The backend runs on :8000 (uvicorn; PLATINA_API_PORT to change it); /api/* is proxied to it.
const api = `http://127.0.0.1:${process.env.PLATINA_API_PORT ?? 8000}`;

export default defineConfig({
  server: {
    proxy: {
      "/api": { target: api, rewrite: (p) => p.replace(/^\/api/, "") },
    },
  },
});
