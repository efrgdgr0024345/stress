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
        // Some shared hosts serve .mjs as application/octet-stream. Workers
        // remain ES modules, but use .js so the web server supplies JS MIME.
        assetFileNames: (asset) =>
          asset.names.some((name) => name.endsWith(".mjs"))
            ? "assets/[name]-[hash].js"
            : "assets/[name]-[hash][extname]",
        manualChunks: { pdf: ["pdfjs-dist"], react: ["react", "react-dom"] },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8010" } },
});
