#!/usr/bin/env python3
"""
Convert OpenAI Codex CLI session JSONL files to Markdown.

Reads from ~/.codex/sessions/ (or CODEX_SESSIONS_DIR) and produces
one markdown file per session in the output directory.

Format: each session is a single JSONL file containing event records
with types like user_message, agent_message, function_call, etc.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) > 1 else Path.home() / ".codex" / "sessions"
DST = Path(sys.argv[2]).expanduser().resolve() if len(sys.argv) > 2 else Path.cwd() / "markdown_codex"


def sanitize_home_paths(text: str) -> str:
    """Replace home directory paths with ~ to avoid exposing usernames."""
    home = str(Path.home())
    text = text.replace(home, "~")
    # Also catch /Users/<name> or /home/<name> patterns
    text = re.sub(r"/(?:Users|home)/[a-zA-Z0-9._-]+", "~", text)
    return text


def parse_session(session_path: Path) -> dict:
    """Parse a Codex session JSONL file into a structured dict."""
    records = []
    for line in session_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        return None

    # Extract session metadata
    session_id = None
    session_ts = None
    cwd = None
    for rec in records:
        if rec.get("type") == "session_meta":
            p = rec.get("payload", {})
            session_id = p.get("id", session_path.stem)
            session_ts = p.get("timestamp")
            cwd = p.get("cwd", "")
            break

    if not session_id:
        session_id = session_path.stem
    if not session_ts:
        session_ts = records[0].get("timestamp", "unknown")

    # Build markdown blocks
    blocks = []
    entry_num = 0

    for rec in records:
        ts = rec.get("timestamp", "")
        payload = rec.get("payload", {})
        rec_type = rec.get("type", "")
        inner_type = payload.get("type", "")

        # User message
        if inner_type == "user_message":
            entry_num += 1
            msg = payload.get("message", "")
            msg = sanitize_home_paths(msg)
            blocks.append(
                f"\n>>>USER_REQUEST<<<\n"
                f"# User #{entry_num} — {ts}\n\n"
                f"{msg}\n"
            )

        # Agent message (commentary or final response)
        elif inner_type == "agent_message":
            entry_num += 1
            msg = sanitize_home_paths(payload.get("message", ""))
            phase = payload.get("phase", "")
            label = "Agent Commentary" if phase == "commentary" else "Agent"
            blocks.append(
                f"\n### {label} #{entry_num} — {ts}\n\n"
                f"{msg}\n"
            )

        # Function call (tool use)
        elif inner_type == "function_call":
            entry_num += 1
            name = payload.get("name", "unknown")
            args_str = payload.get("arguments", "{}")
            try:
                args = json.loads(args_str)
                args_str = json.dumps(args, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
            args_str = sanitize_home_paths(args_str)
            blocks.append(
                f"\n### Tool Call #{entry_num} — {ts}\n\n"
                f"**Tool Call: `{name}`**\n"
                f"```json\n{args_str}\n```\n"
            )

        # Function call output
        elif inner_type == "function_call_output":
            entry_num += 1
            output = sanitize_home_paths(payload.get("output", ""))
            blocks.append(
                f"\n### Tool Output #{entry_num} — {ts}\n\n"
                f"```\n{output}\n```\n"
            )

        # Reasoning
        elif inner_type == "reasoning":
            # Skip reasoning blocks (internal)
            continue

        # Token count
        elif inner_type == "token_count":
            continue

        # Task lifecycle
        elif inner_type in ("task_started", "task_complete"):
            continue

    # Determine project name from cwd
    cwd_clean = sanitize_home_paths(cwd or "unknown")
    project_name = cwd_clean.replace("~/", "").replace("/", "-") if cwd_clean != "unknown" else "codex-session"

    return {
        "session_id": session_id,
        "timestamp": session_ts,
        "cwd": cwd_clean,
        "project_name": project_name,
        "blocks": blocks,
        "entry_count": entry_num,
    }


def convert_all_sessions():
    """Convert all Codex session files to markdown."""
    if not SRC.exists():
        print(f"Codex sessions directory not found: {SRC}")
        return

    session_files = sorted(SRC.rglob("*.jsonl"))
    if not session_files:
        print(f"No session files found in {SRC}")
        return

    DST.mkdir(parents=True, exist_ok=True)

    # Group sessions by project (cwd)
    projects: dict[str, list] = {}
    for sf in session_files:
        parsed = parse_session(sf)
        if not parsed or not parsed["blocks"]:
            continue
        proj = parsed["project_name"]
        if proj not in projects:
            projects[proj] = []
        projects[proj].append(parsed)

    # Sort sessions within each project by timestamp
    for proj in projects:
        projects[proj].sort(key=lambda s: s["timestamp"] or "")

    # Write one markdown file per project
    for proj_name, sessions in projects.items():
        out_path = DST / f"{proj_name}.md"

        header = [
            f"# {proj_name}",
            "",
            f"Codex CLI conversations from project `{proj_name}`.",
            "",
            f"Total sessions: {len(sessions)}",
            "",
            "---",
            "",
        ]

        body_blocks = []
        for session in sessions:
            body_blocks.append(
                f"\n---\n\n## Session `{session['session_id'][:8]}` "
                f"(started {session['timestamp']})\n"
            )
            body_blocks.extend(session["blocks"])

        content = "\n".join(header) + "\n".join(body_blocks)
        out_path.write_text(content, encoding="utf-8")

        total_entries = sum(s["entry_count"] for s in sessions)
        print(f"  {proj_name}: {len(sessions)} sessions, {total_entries} entries")

    print(f"\nDone. {len(projects)} project files written to {DST}")


if __name__ == "__main__":
    convert_all_sessions()
