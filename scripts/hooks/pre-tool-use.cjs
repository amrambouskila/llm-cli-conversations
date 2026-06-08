const { emit, fileExists } = require("./hookUtils.cjs");

// Fires on Glob|Grep (matcher set in settings). Nudges toward the prebuilt graph.
function main() {
  if (fileExists("graphify-out/graph.json")) {
    emit({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        additionalContext:
          "graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files.",
      },
    });
  }
}

try {
  main();
} catch (e) {
  process.stderr.write(`[hook] pre-tool-use failed: ${e.message}\n`);
  process.exitCode = 0;
}
