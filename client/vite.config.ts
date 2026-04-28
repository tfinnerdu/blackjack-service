import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Build output goes straight into the Flask static folder so gunicorn
// serves the bundle without an extra copy step.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: path.resolve(__dirname, "../app/static"),
    emptyOutDir: true,
  },
  server: {
    // host=true binds to 0.0.0.0 so other machines on the LAN can reach
    // the dev server by COMPUTERNAME or LAN IP, not just localhost.
    host: true,
    port: 5174,
    proxy: {
      "/api": "http://127.0.0.1:5050",
      "/health": "http://127.0.0.1:5050",
    },
  },
});
