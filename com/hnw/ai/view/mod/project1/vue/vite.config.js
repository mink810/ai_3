import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
export default defineConfig({
    plugins: [vue()],
    server: {
        port: 5174,
        strictPort: true,
        proxy: {
            "/request": { target: "http://127.0.0.1:8020", changeOrigin: true },
            "/ws": { target: "ws://127.0.0.1:8020", ws: true, changeOrigin: true }
        }
    },
    build: {
        outDir: "dist",
        sourcemap: false
    }
});
