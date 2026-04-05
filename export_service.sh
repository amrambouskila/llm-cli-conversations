#!/usr/bin/env bash
set -e

# ============================================================
#              CONFIGURATION (EDIT THESE ONLY)
# ============================================================
SERVICE_PREFIX="llm-cli-conversation-export"
COMPOSE_FILE="docker-compose.yml"
PORT="${PORT:-5050}"
SUMMARY_MODEL="${SUMMARY_MODEL:-claude-haiku-4-5-20251001}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

SUMMARY_DIR="$SCRIPT_DIR/browser_state/summaries"
WATCHER_PID=""

# ============================================================
#                     HELPERS
# ============================================================
check_docker() {
  if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is not installed or not on PATH."
    echo "  Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
  fi
  if ! docker info &>/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not running. Please start Docker Desktop."
    exit 1
  fi
}

check_python() {
  if command -v python3 &>/dev/null; then
    PYTHON=python3
  elif command -v python &>/dev/null; then
    PYTHON=python
  else
    echo "ERROR: Python is not installed or not on PATH."
    exit 1
  fi
}

remove_images() {
  echo ""
  echo "Searching for images starting with \"$SERVICE_PREFIX\"..."
  FOUND=0
  for IMAGE in $(docker images --format "{{.Repository}}:{{.Tag}}" | grep -i "^${SERVICE_PREFIX}"); do
      echo "Found image: $IMAGE"
      echo "Removing image $IMAGE..."
      docker rmi -f "$IMAGE" 2>/dev/null || true
      FOUND=1
  done
  if [[ $FOUND -eq 0 ]]; then
      echo "No images found matching prefix \"$SERVICE_PREFIX\"."
  fi
}

wipe_generated_data() {
  echo ""
  echo "Removing generated data (raw/, markdown/, markdown_codex/, browser_state/)..."
  rm -rf "$SCRIPT_DIR/raw" "$SCRIPT_DIR/markdown" "$SCRIPT_DIR/markdown_codex" "$SCRIPT_DIR/browser_state"
  echo "Done. Source data in ~/.claude/projects/ is untouched."
}

run_export() {
  check_python
  echo "==> Exporting conversations..."
  if [ -n "$FILTER" ]; then
    "$PYTHON" convert_export.py "$FILTER"
  else
    "$PYTHON" convert_export.py
  fi
  echo ""
  # Also export Codex sessions if available
  CODEX_SRC="${CODEX_SESSIONS_DIR:-$HOME/.codex/sessions}"
  if [ -d "$CODEX_SRC" ]; then
    echo "==> Exporting Codex sessions..."
    "$PYTHON" convert_codex_sessions.py "$CODEX_SRC" "$SCRIPT_DIR/markdown_codex"
    echo ""
  fi
}

# ============================================================
#       SUMMARY WATCHER — runs on the host, uses local claude
# ============================================================
start_summary_watcher() {
  if ! command -v claude &>/dev/null; then
    echo "    Note: 'claude' CLI not found — AI summaries disabled."
    echo "    Install the AI CLI to enable: https://docs.anthropic.com/en/docs/claude-code"
    return
  fi

  mkdir -p "$SUMMARY_DIR"

  (
    while true; do
      for req in "$SUMMARY_DIR"/*.pending; do
        [ -f "$req" ] || continue
        id=$(basename "$req" .pending)
        input="$SUMMARY_DIR/${id}.input"
        output="$SUMMARY_DIR/${id}.md"

        if [ ! -f "$input" ]; then
          rm -f "$req"
          continue
        fi

        # Truncate large inputs to ~100K chars (~25K tokens) to stay within context limits.
        # Keeps the first 50K and last 50K chars so the summary sees the beginning and end.
        input_size=$(wc -c < "$input" | tr -d ' ')
        truncated="$SUMMARY_DIR/${id}.truncated"
        if [ "$input_size" -gt 100000 ]; then
          head -c 50000 "$input" > "$truncated"
          printf '\n\n[... %s characters truncated for summary ...]\n\n' "$((input_size - 100000))" >> "$truncated"
          tail -c 50000 "$input" >> "$truncated"
        else
          cp "$input" "$truncated"
        fi

        # Generate summary using claude CLI
        if claude -p --model "$SUMMARY_MODEL" \
          "You are a summarization tool. Your ONLY job is to output a summary. Do NOT ask for permission, clarification, or confirmation. Do NOT say you need more context. Do NOT refuse. Just summarize whatever text is provided to the best of your ability.

Your first line MUST be exactly: TITLE: <short title under 8 words>
Then a blank line, then a concise summary (under 300 words, markdown).
Focus on: what the user asked for, what was done, and the outcome. If the text is truncated or incomplete, summarize what you can see." \
          < "$truncated" > "$output.tmp" 2>/dev/null; then
          mv "$output.tmp" "$output"
        else
          printf 'TITLE: Summary failed\n\n**Summary generation failed.** The input may be too large or the claude CLI may not be authenticated. Run `claude` in a terminal to check.' > "$output"
        fi

        rm -f "$truncated"

        rm -f "$req" "$input" "$output.tmp"
      done
      sleep 2
    done
  ) &
  WATCHER_PID=$!
  echo "    Summary watcher started (PID $WATCHER_PID, model: $SUMMARY_MODEL)"
}

stop_summary_watcher() {
  if [ -n "$WATCHER_PID" ]; then
    kill "$WATCHER_PID" 2>/dev/null || true
    wait "$WATCHER_PID" 2>/dev/null || true
    WATCHER_PID=""
    echo "    Summary watcher stopped."
  fi
}

# Ensure watcher is killed on script exit
trap stop_summary_watcher EXIT

# ============================================================
#                  PARSE ARGUMENTS
# ============================================================
SKIP_EXPORT=false
EXPORT_ONLY=false
FILTER=""
for arg in "$@"; do
  case "$arg" in
    --skip-export) SKIP_EXPORT=true ;;
    --export-only) EXPORT_ONLY=true ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS] [project-filter]"
      echo ""
      echo "Options:"
      echo "  --skip-export   Start browser without re-exporting conversations"
      echo "  --export-only   Export conversations only, don't start browser"
      echo "  -h, --help      Show this help"
      echo ""
      echo "Arguments:"
      echo "  project-filter  Only export projects matching this string"
      echo ""
      echo "Environment:"
      echo "  PORT              Server port (default: 5050)"
      echo "  SUMMARY_MODEL     Claude model for summaries (default: claude-haiku-4-5-20251001)"
      exit 0
      ;;
    -*) ;;
    *) FILTER="$arg" ;;
  esac
done

if [ "$EXPORT_ONLY" = true ]; then
  run_export
  echo "Export complete. Markdown files are in: $SCRIPT_DIR/markdown/"
  exit 0
fi

# ============================================================
#                  EXPORT CONVERSATIONS
# ============================================================
if [ "$SKIP_EXPORT" = false ]; then
  run_export
fi

# Check that markdown files exist
if [ ! -d "$SCRIPT_DIR/markdown" ] || [ -z "$(ls -A "$SCRIPT_DIR/markdown/"*.md 2>/dev/null)" ]; then
  echo "ERROR: No markdown files found in ./markdown/"
  echo "  Run without --skip-export to generate them first."
  exit 1
fi

# ============================================================
#                     RUN DOCKER COMPOSE
# ============================================================
check_docker

echo "==> Starting Docker Compose..."
PORT="$PORT" docker compose -f "$COMPOSE_FILE" up --build -d

echo "==> Starting summary watcher..."
start_summary_watcher

echo ""
echo "=============================="
echo "Service running at http://localhost:$PORT"
echo ""
echo "Press k + Enter = stop but keep image"
echo "Press q + Enter = stop & remove image"
echo "Press v + Enter = stop, remove image, volumes & generated data"
echo "Press r + Enter = full reset & restart (wipe, re-export, rebuild)"
echo "=============================="

# Auto-open browser
if command -v open &>/dev/null; then
  sleep 2
  open "http://localhost:$PORT"
elif command -v xdg-open &>/dev/null; then
  sleep 2
  xdg-open "http://localhost:$PORT"
fi

while true; do
    read -rp "Enter selection (k/q/v/r): " CHOICE
    CHOICE=$(printf '%s' "$CHOICE" | tr '[:upper:]' '[:lower:]')
    case "$CHOICE" in
        k)
            echo ""
            echo "Stopping containers but keeping images..."
            stop_summary_watcher
            docker compose -f "$COMPOSE_FILE" down
            exit 0
            ;;
        q)
            echo ""
            echo "Stopping and removing all containers..."
            stop_summary_watcher
            docker compose -f "$COMPOSE_FILE" down --remove-orphans
            remove_images
            exit 0
            ;;
        v)
            echo ""
            echo "Stopping and removing all containers and volumes..."
            stop_summary_watcher
            docker compose -f "$COMPOSE_FILE" down --volumes --remove-orphans
            remove_images
            wipe_generated_data
            exit 0
            ;;
        r)
            echo ""
            echo "==> Full reset & restart..."

            stop_summary_watcher
            docker compose -f "$COMPOSE_FILE" down --volumes --remove-orphans
            remove_images
            wipe_generated_data

            run_export

            echo "==> Rebuilding Docker image..."
            PORT="$PORT" docker compose -f "$COMPOSE_FILE" up --build -d

            echo "==> Starting summary watcher..."
            start_summary_watcher

            echo ""
            echo "=============================="
            echo "Service restarted at http://localhost:$PORT"
            echo ""
            echo "Press k + Enter = stop but keep image"
            echo "Press q + Enter = stop & remove image"
            echo "Press v + Enter = stop, remove image, volumes & generated data"
            echo "Press r + Enter = full reset & restart (wipe, re-export, rebuild)"
            echo "=============================="

            if command -v open &>/dev/null; then
              sleep 2
              open "http://localhost:$PORT"
            elif command -v xdg-open &>/dev/null; then
              sleep 2
              xdg-open "http://localhost:$PORT"
            fi
            # Loop back to wait for next selection
            ;;
        *) echo "Invalid selection. Enter k, q, v, or r." ;;
    esac
done
