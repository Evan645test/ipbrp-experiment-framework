import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const root = fileURLToPath(new URL("./", import.meta.url));
const base = process.env.READER_BASE_PATH ?? "/";
if (!base.startsWith("/") || !base.endsWith("/") || base.includes("..") || /[?#]/.test(base)) {
  throw new Error("READER_BASE_PATH 必須為以 / 開頭及結尾的網站路徑。");
}

export default defineConfig({
  root: `${root}static`,
  publicDir: `${root}public`,
  base,
  plugins: [react()],
  resolve: {
    alias: [
      { find: "next/image", replacement: `${root}static/image.tsx` },
      { find: "@", replacement: root },
    ],
  },
  css: { postcss: `${root}postcss.config.mjs` },
  build: { outDir: `${root}dist-static`, emptyOutDir: true },
});
