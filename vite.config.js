import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const frontendPort = Number(process.env.YZWCLOUD_FRONTEND_PORT || process.env.PORT || 10000);
const frontendHost = process.env.YZWCLOUD_FRONTEND_HOST || "0.0.0.0";
const backendPort = process.env.YZWCLOUD_BACKEND_PORT || "10001";
const backendTarget = process.env.YZWCLOUD_DEV_BACKEND_URL || `http://127.0.0.1:${backendPort}`;

export default defineConfig(({ command }) => ({
  base: command === "serve" ? "/" : "/static/",
  plugins: [react()],
  root: "web",
  build: {
    outDir: "../src/yzwcloud/static",
    emptyOutDir: false,
  },
  server: {
    host: frontendHost,
    port: frontendPort,
    headers: {
      "Cache-Control": "no-store",
    },
    proxy: {
      "/api": backendTarget,
      "/static": backendTarget,
    },
  },
}));
