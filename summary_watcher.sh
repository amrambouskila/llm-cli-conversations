#!/usr/bin/env bash
# macOS/Linux counterpart of summary_watcher.bat — host-side claude CLI watcher
# that turns *.pending summary jobs into *.md summaries.
set -u

SUMMARY_MODEL="${SUMMARY_MODEL:-claude-sonnet-4-6}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUMMARY_DIR="$SCRIPT_DIR/browser_state/summaries"
PID_FILE="$SCRIPT_DIR/browser_state/summary_watcher.pid"

mkdir -p "$SUMMARY_DIR"
echo "$$" > "$PID_FILE"

PROMPT="You are a summarization tool. Your ONLY job is to output a summary. Do NOT ask for permission, clarification, or confirmation. Do NOT say you need more context. Do NOT refuse. Just summarize whatever text is provided to the best of your ability. Your first line MUST be exactly: TITLE: <short title under 8 words>. Then a blank line, then a concise summary (under 300 words, markdown). Focus on: what the user asked for, what was done, and the outcome. If the text is truncated or incomplete, summarize what you can see."

while true; do
  for pending in "$SUMMARY_DIR"/*.pending; do
    [ -e "$pending" ] || continue
    base="$(basename "$pending" .pending)"
    input="$SUMMARY_DIR/$base.input"
    output="$SUMMARY_DIR/$base.md"

    if [ -f "$input" ]; then
      # Safety net only: backend hierarchical summarization keeps individual
      # jobs around 80K chars. Anything larger than 400K (~100K tokens) gets
      # head/tail truncated so it still fits in the sonnet context window.
      truncated="${TMPDIR:-/tmp}/claude_summary_input.tmp"
      fsize=$(wc -c < "$input" | tr -d ' ')
      if [ "$fsize" -gt 400000 ]; then
        cut=$((fsize - 400000))
        {
          head -c 200000 "$input"
          printf '\n\n[... %s characters truncated for summary ...]\n\n' "$cut"
          tail -c 200000 "$input"
        } > "$truncated"
      else
        cp -f "$input" "$truncated"
      fi

      if claude -p --model "$SUMMARY_MODEL" "$PROMPT" < "$truncated" > "$output.tmp" 2>/dev/null && [ -s "$output.tmp" ]; then
        mv -f "$output.tmp" "$output"
      else
        printf 'TITLE: Summary failed\n\n**Summary generation failed.** The input may be too large or the claude CLI may not be authenticated.\n' > "$output"
      fi
      rm -f "$truncated"
    fi
    rm -f "$pending" "$input" "$output.tmp"
  done
  sleep 2
done
