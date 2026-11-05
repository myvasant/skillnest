import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { contentPlugin } from "./scripts/vite-content-plugin.ts";

export default defineConfig({
  plugins: [react(), tailwindcss(), contentPlugin()],
  worker: { format: "es" },
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 900,
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}", "tests/unit/**/*.test.{ts,tsx}", "tests/content/**/*.test.ts"],
    testTimeout: 60_000,
    hookTimeout: 120_000,
  },
});
