import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发模式下 /api 代理到本机后端（默认 8000）；生产由 FastAPI 托管静态文件
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
