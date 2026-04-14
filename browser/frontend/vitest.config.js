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
      // Per-file gates for the modules covered by phase 6.6. Floors match
      // current achievement minus a small fluctuation buffer. Phase 7
      // adds entries here as components get extracted and tested.
      thresholds: {
        "src/utils.js": { lines: 95, branches: 85, functions: 100 },
        "src/components/SearchResults.jsx": {
          lines: 100,
          branches: 95,
          functions: 100,
        },
        "src/components/FilterChips.jsx": {
          lines: 95,
          branches: 85,
          functions: 100,
        },
        "src/components/MetadataPanel.jsx": {
          lines: 100,
          branches: 100,
          functions: 100,
        },
        "src/App.jsx": { lines: 70, branches: 65, functions: 50 },
      },
    },
  },
});
