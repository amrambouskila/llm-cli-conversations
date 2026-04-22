import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/__tests__/setup.js"],
    include: ["src/__tests__/**/*.test.{js,jsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "text-summary", "json", "html"],
      include: ["src/**/*.{js,jsx}"],
      exclude: ["src/__tests__/**", "src/main.jsx"],
      // v2.1.1 final: every src/ module at 100% lines + branches + functions.
      // Residual sub-100 paths that are genuinely unreachable under the React
      // test flow (stale-closure guards, defensive null fallbacks in render
      // pipelines) are scoped via `/* c8 ignore */` pragmas in the source
      // files — never via per-file threshold reductions here.
      thresholds: {
        lines: 100,
        functions: 100,
        branches: 100,
      },
    },
  },
});
