"""Extract model names and token usage from raw JSONL conversation files.

Claude JSONL: each file is one conversation, filename UUID = sessionId.
  - model from first assistant record's message.model
  - per-turn usage from message.usage (input_tokens, output_tokens,
    cache_read_input_tokens, cache_creation_input_tokens)
  - aggregated session totals

Codex JSONL: model/usage not reliably available.
  - model_provider from session_meta payload
  - no per-turn token usage; fall back to char_count // 4
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SessionMetadata:
    session_id: str
    model: str | None = None
    model_provider: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


def _read_claude_jsonl(jsonl_path: Path) -> SessionMetadata | None:
    """Parse a single Claude JSONL file and extract session metadata."""
    session_id = jsonl_path.stem
    # Skip subagent files
    if "/subagents/" in str(jsonl_path):
        return None

    meta = SessionMetadata(session_id=session_id)
    model_found = False

    try:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("type") != "assistant":
                continue

            msg = record.get("message", {})

            if not model_found and msg.get("model"):
                meta.model = msg["model"]
                model_found = True

            usage = msg.get("usage", {})
            meta.input_tokens += usage.get("input_tokens", 0)
            meta.output_tokens += usage.get("output_tokens", 0)
            meta.cache_read_tokens += usage.get("cache_read_input_tokens", 0)
            meta.cache_creation_tokens += usage.get("cache_creation_input_tokens", 0)
    except (OSError, UnicodeDecodeError):
        return None

    return meta


def _read_codex_jsonl(jsonl_path: Path) -> SessionMetadata | None:
    """Parse a single Codex JSONL file and extract session metadata."""
    meta = None

    try:
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            if record.get("type") == "session_meta":
                payload = record.get("payload", {})
                session_id = payload.get("id", jsonl_path.stem)
                meta = SessionMetadata(
                    session_id=session_id,
                    model_provider=payload.get("model_provider"),
                )
                break
    except (OSError, UnicodeDecodeError):
        return None

    return meta


def read_claude_metadata(raw_projects_dir: str) -> dict[str, SessionMetadata]:
    """Scan all Claude JSONL files and return per-session metadata.

    Keys are session/conversation UUIDs (the JSONL filename stems).
    """
    results: dict[str, SessionMetadata] = {}
    base = Path(raw_projects_dir)
    if not base.exists():
        return results

    for project_dir in sorted(base.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            meta = _read_claude_jsonl(jsonl_file)
            if meta:
                results[meta.session_id] = meta

    return results


def read_codex_metadata(codex_sessions_dir: str) -> dict[str, SessionMetadata]:
    """Scan all Codex JSONL files and return per-session metadata.

    Keys are session UUIDs from session_meta payload.
    """
    results: dict[str, SessionMetadata] = {}
    base = Path(codex_sessions_dir)
    if not base.exists():
        return results

    for jsonl_file in base.rglob("*.jsonl"):
        meta = _read_codex_jsonl(jsonl_file)
        if meta:
            results[meta.session_id] = meta

    return results
