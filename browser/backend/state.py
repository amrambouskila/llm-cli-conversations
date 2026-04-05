"""
Persistent browser state — soft-delete (hide/restore) for segments,
conversations, and projects.

State is stored in a JSON file on a mounted volume so it survives
container restarts but is independent of the exported data.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

STATE_DIR = os.environ.get("STATE_DIR", "/data/state")
STATE_FILE = Path(STATE_DIR) / "browser_state.json"

_lock = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _load() -> dict:
    """Load state from disk. Returns default structure if missing/corrupt."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[state] Warning: could not load {STATE_FILE}, resetting to default: {e}")
    return {
        "hidden_segments": {},      # segment_id -> iso timestamp
        "hidden_conversations": {}, # "project::conv_id" -> iso timestamp
        "hidden_projects": {},      # project_name -> iso timestamp
    }


def _save(state: dict) -> None:
    """Write state to disk atomically."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_state() -> dict:
    with _lock:
        return _load()


def hide_segment(segment_id: str) -> dict:
    with _lock:
        state = _load()
        state["hidden_segments"][segment_id] = _now_iso()
        _save(state)
        return state


def restore_segment(segment_id: str) -> dict:
    with _lock:
        state = _load()
        state["hidden_segments"].pop(segment_id, None)
        _save(state)
        return state


def hide_conversation(project_name: str, conversation_id: str) -> dict:
    with _lock:
        state = _load()
        key = f"{project_name}::{conversation_id}"
        state["hidden_conversations"][key] = _now_iso()
        _save(state)
        return state


def restore_conversation(project_name: str, conversation_id: str) -> dict:
    with _lock:
        state = _load()
        key = f"{project_name}::{conversation_id}"
        state["hidden_conversations"].pop(key, None)
        _save(state)
        return state


def hide_project(project_name: str) -> dict:
    with _lock:
        state = _load()
        state["hidden_projects"][project_name] = _now_iso()
        _save(state)
        return state


def restore_project(project_name: str) -> dict:
    with _lock:
        state = _load()
        state["hidden_projects"].pop(project_name, None)
        _save(state)
        return state


def restore_all() -> dict:
    with _lock:
        state = {
            "hidden_segments": {},
            "hidden_conversations": {},
            "hidden_projects": {},
        }
        _save(state)
        return state


def is_segment_hidden(state: dict, segment: dict) -> bool:
    """Check if a segment is hidden (directly, by conversation, or by project)."""
    if segment["id"] in state.get("hidden_segments", {}):
        return True
    conv_key = f"{segment.get('project_name', '')}::{segment.get('conversation_id', '')}"
    if conv_key in state.get("hidden_conversations", {}):
        return True
    if segment.get("project_name", "") in state.get("hidden_projects", {}):
        return True
    return False


def is_project_hidden(state: dict, project_name: str) -> bool:
    return project_name in state.get("hidden_projects", {})


def hidden_counts(state: dict) -> dict:
    return {
        "segments": len(state.get("hidden_segments", {})),
        "conversations": len(state.get("hidden_conversations", {})),
        "projects": len(state.get("hidden_projects", {})),
    }
