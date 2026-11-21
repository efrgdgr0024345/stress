import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "./",
  root: "apps/web",
  build: {
    outDir: "../../dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: { pdf: ["pdfjs-dist"], react: ["react", "react-dom"] },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8010" } },
});
