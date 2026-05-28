import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig(({ command }) => ({
  base: command === "serve" ? "/" : "/static/",
  plugins: [react()],
  root: "web",
  build: {
    outDir: "../src/yzwcloud/static",
    emptyOutDir: false,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8010",
    },
  },
}));
