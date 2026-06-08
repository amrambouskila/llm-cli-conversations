const childProcess = require("node:child_process");
const fs = require("node:fs");
const { emit, getToolFilePath, readHookPayload } = require("./hookUtils.cjs");

function pythonCmd() {
  for (const cmd of ["python", "python3"]) {
    const r = childProcess.spawnSync(cmd, ["--version"], { encoding: "utf8", windowsHide: true });
    if (r && r.status === 0) return cmd;
  }
  return null;
}

async function main() {
  const payload = await readHookPayload();
  const f = getToolFilePath(payload);
  if (!f) return;

  if (f.endsWith(".py")) {
    const py = pythonCmd();
    if (!py) return;
    const r = childProcess.spawnSync(py, ["-m", "py_compile", f], { encoding: "utf8", windowsHide: true });
    if (r.status !== 0) {
      emit({ hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: `py_compile failed for ${f}:\n${(r.stderr || "").trim()}` } });
    }
    return;
  }

  if (f.endsWith(".json")) {
    try {
      JSON.parse(fs.readFileSync(f, "utf8"));
    } catch {
      emit({ hookSpecificOutput: { hookEventName: "PostToolUse", additionalContext: `Invalid JSON: ${f}` } });
    }
  }
}

main().catch((e) => {
  process.stderr.write(`[hook] post-tool-use failed: ${e.message}\n`);
  process.exitCode = 0;
});
