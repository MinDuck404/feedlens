import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  // Đường dẫn tương đối: chạy được cả dưới /<tên-repo>/ (GitHub Pages) lẫn ở gốc (local, nginx)
  base: "./",
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
