import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": dirname,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    css: true,
    exclude: [
      "**/node_modules/**",
      ".next/**",
      "coverage/**",
      "e2e/**",
      "tests/e2e/**",
      "playwright.config.ts",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["lib/*.ts", "store/**/*.ts"],
      exclude: ["**/*.test.ts", "**/*.test.tsx", "**/__tests__/**"],
      thresholds: {
        branches: 95,
        functions: 95,
        lines: 95,
        statements: 95,
      },
    },
  },
});
