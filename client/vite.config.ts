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
    host: "0.0.0.0",
    port: 5174,
    // Vite 5+ rejects requests whose Host header isn't in this list with a
    // 'Blocked request' page. localhost / 127.0.0.1 cover loopback; we also
    // accept any *.local FQDN so a domain-joined Doane machine reaches by
    // its own hostname (e.g. `MACHINE-1234.doane.local`). Add specific
    // device hostnames here if you're sharing across the LAN.
    allowedHosts: [
      "localhost",
      "127.0.0.1",
      ".local",
    ],
    proxy: {
      "/api": "http://127.0.0.1:5050",
      "/health": "http://127.0.0.1:5050",
    },
  },
});
