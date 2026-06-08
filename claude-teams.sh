#!/usr/bin/env bash
# macOS/Linux counterpart of claude-teams.bat — launch Claude Code with the
# experimental agent-teams flag enabled. Usage: ./claude-teams.sh [claude args...]
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
exec claude "$@"
