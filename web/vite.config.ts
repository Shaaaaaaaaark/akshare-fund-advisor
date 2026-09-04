import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 部署子路径：容器同源部署为默认 "/"；GitHub Pages 项目站点需设为 "/<repo>/"。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const basePath = env.VITE_BASE_PATH || "/";
  return {
    base: basePath,
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": "http://127.0.0.1:8080",
        "/health": "http://127.0.0.1:8080",
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
