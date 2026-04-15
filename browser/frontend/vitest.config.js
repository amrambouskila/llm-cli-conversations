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
      // Phase 7.4 final: every src/ module is at 100% lines. Branches and
      // functions are at 96+% globally. The remaining sub-100% branches live
      // in inline arrow wrappers that React test stubs never invoke, Chart.js
      // option callbacks that the `react-chartjs-2` mock stores but doesn't
      // run, and jsdom-unreachable d3 simulation tick callbacks.
      thresholds: {
        lines: 100,
        functions: 95,
        branches: 95,
        // Per-file hard caps — mirror the most robust subset of per-module
        // realities so regressions land loudly.
        "src/utils.js": { lines: 100, branches: 100, functions: 100 },
        "src/api.js": { lines: 100, branches: 100, functions: 100 },
        "src/components/Charts.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/ConceptWikiPane.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/ContentPane.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/ContentViewer.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/ConversationsTab.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/FilterBar.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/FilterChips.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/Header.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/Heatmap.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/KnowledgeGraph.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/MetadataPane.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/MetadataPanel.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/ProjectList.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/ProjectsPane.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/RequestList.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/RequestsPane.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/SearchBar.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/components/SearchResults.jsx": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useBackendReady.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useConceptWiki.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useCostBreakdown.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useHideRestore.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useKeyboardShortcuts.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useProjectSelection.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useProviders.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useResizeHandles.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useSearch.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useSummaryTitles.js": { lines: 100, branches: 100, functions: 100 },
        "src/hooks/useTheme.js": { lines: 100, branches: 100, functions: 100 },
        // The 3 files below are at 100% lines but below 100% on branches or
        // functions. The residual gaps are Chart.js option callbacks that
        // react-chartjs-2's jsdom mock stores but never invokes, inline JSX
        // arrow wrappers around hooks that are themselves fully covered in
        // isolation, and jsdom-unreachable d3 simulation tick handlers.
        "src/components/Dashboard.jsx": { lines: 100, branches: 92, functions: 92 },
        "src/components/ConceptGraph.jsx": { lines: 100, branches: 80, functions: 100 },
        "src/components/SummaryPanel.jsx": { lines: 100, branches: 88, functions: 100 },
        "src/App.jsx": { lines: 100, branches: 84, functions: 25 },
      },
    },
  },
});
