import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // HTTP API 프록시
      "/request": {
        target: "http://127.0.0.1:8010",
        changeOrigin: true
      },
      // WebSocket 프록시
      "/ws": {
        target: "ws://127.0.0.1:8010",
        ws: true,
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: "dist",
    sourcemap: false
  }
});
