const { emit, projectName, uncommittedFiles } = require("./hookUtils.cjs");

function main() {
  const files = uncommittedFiles();
  if (files.length === 0) {
    return;
  }
  const name = projectName();
  const docsTouched = files.some((f) => f.replace(/\\/g, "/").startsWith("docs/"));
  const parts = [`Uncommitted changes in ${name}: ${files.length} file(s). User manages git — do not run any mutating git command; suggest a commit message only.`];
  if (!docsTouched) {
    parts.push("Source changed but docs/ was not — consider updating docs/status.md and docs/versions.md.");
  }
  emit({ systemMessage: parts.join(" ") });
}

try {
  main();
} catch (error) {
  process.stderr.write(`[hook] stop failed: ${error.message}\n`);
}
