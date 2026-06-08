#!/usr/bin/env bash
# macOS/Linux counterpart of graph_watcher.bat — auto-generate the graphify
# concept graph on startup, then watch for re-generation requests.
set -u

GRAPHIFY_MODEL="${GRAPHIFY_MODEL:-claude-sonnet-4-6}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAPHIFY_OUT="$SCRIPT_DIR/graphify-out"
PID_FILE="$GRAPHIFY_OUT/graph_watcher.pid"

mkdir -p "$GRAPHIFY_OUT"
echo "$$" > "$PID_FILE"

# Clear stale signals.
rm -f "$GRAPHIFY_OUT/.status" "$GRAPHIFY_OUT/.generate_requested"

export GRAPHIFY_MODEL GRAPHIFY_OUT

if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi

# Auto-generate on startup.
"$PY" "$SCRIPT_DIR/graph_extract.py"

# Then watch for re-generation requests.
while true; do
  if [ -f "$GRAPHIFY_OUT/.generate_requested" ]; then
    rm -f "$GRAPHIFY_OUT/.generate_requested"
    # Clear chunk cache for full re-extraction.
    rm -f "$GRAPHIFY_OUT"/.graphify_chunk_*.json
    "$PY" "$SCRIPT_DIR/graph_extract.py"
  fi
  sleep 3
done
