/**
 * Vite config for the upload dashboard (step 1c).
 * API base URL comes from env; no proxy required if CORS is enabled on FastAPI.
 */
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Bind all interfaces so both http://localhost:5173 and http://127.0.0.1:5173 work.
    host: true,
  },
});
