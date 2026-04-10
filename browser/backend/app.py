"""
FastAPI backend for browsing LLM CLI exported conversations.

Serves:
  - REST API at /api/*
  - React static build at / (in production / Docker)

Runs locally with no internet dependency for core browsing.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from parser import build_index
import state as browser_state

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_MARKDOWN_DIR = os.environ.get(
    "MARKDOWN_DIR",
    str(SCRIPT_DIR.parent.parent / "markdown"),
)
STATIC_DIR = os.environ.get(
    "STATIC_DIR",
    str(SCRIPT_DIR.parent / "frontend" / "dist"),
)
CLAUDE_PROJECTS_SRC = os.environ.get(
    "CLAUDE_PROJECTS_SRC",
    str(Path.home() / ".claude" / "projects"),
)
RAW_DIR = os.environ.get(
    "RAW_DIR",
    str(SCRIPT_DIR.parent.parent / "raw"),
)

# Codex paths
CODEX_SESSIONS_SRC = os.environ.get(
    "CODEX_SESSIONS_SRC",
    str(Path.home() / ".codex" / "sessions"),
)
CODEX_MARKDOWN_DIR = os.environ.get(
    "CODEX_MARKDOWN_DIR",
    str(Path(DEFAULT_MARKDOWN_DIR).parent / "markdown_codex"),
)

# Watch mode interval in seconds (0 = disabled)
WATCH_INTERVAL = int(os.environ.get("WATCH_INTERVAL", "30"))

# Summaries directory (inside the state volume)
SUMMARIES_DIR = Path(os.environ.get(
    "STATE_DIR", "/data/state"
)) / "summaries"

# ---------------------------------------------------------------------------
# Index — mutable global, rebuilt by /api/update and watch mode
# ---------------------------------------------------------------------------
print(f"Indexing Claude markdown from: {DEFAULT_MARKDOWN_DIR}")
INDEX = build_index(DEFAULT_MARKDOWN_DIR)
print(f"Claude: {len(INDEX['projects'])} projects, {len(INDEX['segments'])} segments")

print(f"Indexing Codex markdown from: {CODEX_MARKDOWN_DIR}")
CODEX_INDEX = build_index(CODEX_MARKDOWN_DIR)
print(f"Codex: {len(CODEX_INDEX['projects'])} projects, {len(CODEX_INDEX['segments'])} segments")

INDEXES = {"claude": INDEX, "codex": CODEX_INDEX}


def get_index(provider: str = "claude") -> dict:
    """Get the index for the given provider."""
    return INDEXES.get(provider, INDEX)

# Track markdown directory mtime for watch mode
_last_mtime: float = 0.0
_last_codex_mtime: float = 0.0

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app):
    if WATCH_INTERVAL > 0:
        asyncio.create_task(_watch_loop())
        print(f"Watch mode enabled: checking for changes every {WATCH_INTERVAL}s")
    yield

app = FastAPI(title="LLM Conversation Browser", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:5050", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers for the update pipeline
# ---------------------------------------------------------------------------
def sync_directory(src: Path, dst: Path) -> None:
    """Copy new/updated files from src to dst, preserving structure."""
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            dst_file = dst / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            if not dst_file.exists():
                shutil.copy2(item, dst_file)
            elif item.stat().st_mtime > dst_file.stat().st_mtime:
                shutil.copy2(item, dst_file)


def run_export_pipeline() -> dict:
    """Run the full sync + convert pipeline and return a status dict."""
    projects_src = Path(CLAUDE_PROJECTS_SRC)
    raw_dir = Path(RAW_DIR)
    raw_projects_dir = raw_dir / "projects"
    markdown_dir = Path(DEFAULT_MARKDOWN_DIR)
    converter_script = SCRIPT_DIR / "convert_claude_jsonl_to_md.py"

    log_lines = []

    if not projects_src.exists():
        return {
            "success": False,
            "error": f"Claude projects directory not found: {projects_src}",
            "log": [],
        }

    project_dirs = sorted(d for d in projects_src.iterdir() if d.is_dir())
    if not project_dirs:
        return {
            "success": False,
            "error": "No project directories found in source.",
            "log": [],
        }

    log_lines.append(f"Found {len(project_dirs)} projects in {projects_src}")

    raw_projects_dir.mkdir(parents=True, exist_ok=True)
    for pd in project_dirs:
        jsonl_count = len(list(pd.glob("*.jsonl")))
        log_lines.append(f"  Syncing {pd.name} ({jsonl_count} conversations)")
        sync_directory(pd, raw_projects_dir / pd.name)

    manifest_path = raw_dir / "manifest.txt"
    jsonl_files = sorted(str(f) for f in raw_projects_dir.rglob("*.jsonl"))
    manifest_path.write_text("\n".join(jsonl_files) + "\n", encoding="utf-8")
    log_lines.append(f"Manifest: {len(jsonl_files)} .jsonl files")

    # Wipe existing markdown files before re-converting to prevent
    # duplicates from different naming schemes (host vs Docker home paths)
    markdown_dir.mkdir(parents=True, exist_ok=True)
    for old_md in markdown_dir.glob("*.md"):
        old_md.unlink()

    result = subprocess.run(
        [sys.executable, str(converter_script), str(raw_projects_dir), str(markdown_dir)],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        log_lines.extend(result.stdout.strip().split("\n"))
    if result.returncode != 0:
        err = result.stderr.strip() if result.stderr else "unknown error"
        return {
            "success": False,
            "error": f"Conversion failed: {err}",
            "log": log_lines,
        }

    global INDEX, CODEX_INDEX
    INDEX = build_index(str(markdown_dir))
    INDEXES["claude"] = INDEX
    log_lines.append(f"Claude re-indexed: {len(INDEX['projects'])} projects, {len(INDEX['segments'])} segments")

    # Also convert Codex sessions if available
    codex_converter = SCRIPT_DIR / "convert_codex_sessions.py"
    codex_src = Path(CODEX_SESSIONS_SRC)
    codex_md = Path(CODEX_MARKDOWN_DIR)
    if codex_src.exists() and codex_converter.exists():
        codex_md.mkdir(parents=True, exist_ok=True)
        # Wipe old codex markdown
        for old_md in codex_md.glob("*.md"):
            old_md.unlink()
        cx_result = subprocess.run(
            [sys.executable, str(codex_converter), str(codex_src), str(codex_md)],
            capture_output=True, text=True,
        )
        if cx_result.stdout:
            log_lines.extend(cx_result.stdout.strip().split("\n"))
        CODEX_INDEX = build_index(str(codex_md))
        INDEXES["codex"] = CODEX_INDEX
        log_lines.append(f"Codex re-indexed: {len(CODEX_INDEX['projects'])} projects, {len(CODEX_INDEX['segments'])} segments")

    return {
        "success": True,
        "projects": len(INDEX["projects"]) + len(CODEX_INDEX["projects"]),
        "segments": len(INDEX["segments"]) + len(CODEX_INDEX["segments"]),
        "log": log_lines,
    }


def _get_dir_mtime(directory: str) -> float:
    """Get the most recent mtime of any file in a directory."""
    best = 0.0
    d = Path(directory)
    if d.exists():
        for f in d.glob("*.md"):
            best = max(best, f.stat().st_mtime)
    return best


# ---------------------------------------------------------------------------
# Watch mode — poll markdown directory for changes
# ---------------------------------------------------------------------------
async def _watch_loop():
    """Background task that re-indexes when markdown files change on disk."""
    global INDEX, CODEX_INDEX, _last_mtime, _last_codex_mtime
    _last_mtime = _get_dir_mtime(DEFAULT_MARKDOWN_DIR)
    _last_codex_mtime = _get_dir_mtime(CODEX_MARKDOWN_DIR)

    while True:
        await asyncio.sleep(WATCH_INTERVAL)
        current = _get_dir_mtime(DEFAULT_MARKDOWN_DIR)
        codex_current = _get_dir_mtime(CODEX_MARKDOWN_DIR)
        changed = False
        if current > _last_mtime:
            _last_mtime = current
            INDEX = build_index(DEFAULT_MARKDOWN_DIR)
            INDEXES["claude"] = INDEX
            changed = True
        if codex_current > _last_codex_mtime:
            _last_codex_mtime = codex_current
            CODEX_INDEX = build_index(CODEX_MARKDOWN_DIR)
            INDEXES["codex"] = CODEX_INDEX
            changed = True
        if changed:
            print(f"[watch] Re-indexed: Claude {len(INDEX['projects'])}p/{len(INDEX['segments'])}s, Codex {len(CODEX_INDEX['projects'])}p/{len(CODEX_INDEX['segments'])}s")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/providers")
def api_providers():
    """Return available providers and their project counts."""
    return [
        {"id": pid, "name": pid.title(), "projects": len(idx["projects"]), "segments": len(idx["segments"])}
        for pid, idx in INDEXES.items()
        if len(idx["projects"]) > 0 or pid == "claude"
    ]


@app.get("/api/projects")
def api_projects(show_hidden: bool = False, provider: str = "claude"):
    """Return list of projects with summaries including per-project stats."""
    idx = get_index(provider)
    st = browser_state.get_state()
    result = []
    for p in idx["projects"]:
        hidden = browser_state.is_project_hidden(st, p["name"])
        if hidden and not show_hidden:
            continue

        # Compute per-project stats (on visible segments only)
        total_chars = 0
        total_words = 0
        total_tools = 0
        timestamps = []
        conv_ids = set()
        conv_first_ts: dict[str, str] = {}
        visible_count = 0
        request_sizes = []
        agg_tool_breakdown: dict[str, int] = {}
        for seg in p["segments"]:
            seg_hidden = browser_state.is_segment_hidden(st, seg)
            if seg_hidden and not show_hidden:
                continue
            visible_count += 1
            total_chars += seg["metrics"]["char_count"]
            total_words += seg["metrics"]["word_count"]
            total_tools += seg["metrics"]["tool_call_count"]
            request_sizes.append(seg["metrics"]["word_count"])
            if seg.get("timestamp"):
                timestamps.append(seg["timestamp"])
            cid = seg.get("conversation_id")
            if cid:
                conv_ids.add(cid)
                if cid not in conv_first_ts and seg.get("timestamp"):
                    conv_first_ts[cid] = seg["timestamp"]
            for tool, cnt in seg.get("tool_breakdown", {}).items():
                agg_tool_breakdown[tool] = agg_tool_breakdown.get(tool, 0) + cnt

        timestamps.sort()
        # Conversation timeline: list of first-timestamps per conversation
        conv_timeline = sorted(conv_first_ts.values())

        result.append({
            "name": p["name"],
            "display_name": p["display_name"],
            "total_requests": visible_count,
            "total_files": p["total_files"],
            "hidden": hidden,
            "stats": {
                "total_conversations": len(conv_ids),
                "total_words": total_words,
                "total_chars": total_chars,
                "estimated_tokens": total_chars // 4,
                "total_tool_calls": total_tools,
                "first_timestamp": timestamps[0] if timestamps else None,
                "last_timestamp": timestamps[-1] if timestamps else None,
                "request_sizes": request_sizes,
                "conversation_timeline": conv_timeline,
                "tool_breakdown": dict(sorted(agg_tool_breakdown.items(), key=lambda x: -x[1])),
            },
        })
    return result


@app.get("/api/projects/{project_name}/segments")
def api_project_segments(project_name: str, show_hidden: bool = False, provider: str = "claude"):
    """Return segment list for a project (previews, no full content)."""
    idx = get_index(provider)
    st = browser_state.get_state()
    for p in idx["projects"]:
        if p["name"] == project_name:
            result = []
            for seg in p["segments"]:
                seg_hidden = browser_state.is_segment_hidden(st, seg)
                if seg_hidden and not show_hidden:
                    continue
                result.append({**seg, "hidden": seg_hidden})
            return result
    return JSONResponse({"error": "project not found"}, status_code=404)


@app.get("/api/projects/{project_name}/conversation/{conversation_id}")
def api_conversation_view(project_name: str, conversation_id: str, provider: str = "claude"):
    """Return all segments for a single conversation, concatenated."""
    idx = get_index(provider)
    for p in idx["projects"]:
        if p["name"] == project_name:
            conv_segments = [
                idx["segments"][s["id"]]
                for s in p["segments"]
                if s.get("conversation_id") == conversation_id
                and s.get("project_name") == project_name
                and s["id"] in idx["segments"]
            ]
            if not conv_segments:
                return JSONResponse({"error": "conversation not found"}, status_code=404)
            combined_markdown = "\n\n---\n\n".join(
                seg["raw_markdown"] for seg in conv_segments
            )
            total_chars = sum(s["metrics"]["char_count"] for s in conv_segments)
            total_words = sum(s["metrics"]["word_count"] for s in conv_segments)
            total_tools = sum(s["metrics"]["tool_call_count"] for s in conv_segments)
            return {
                "conversation_id": conversation_id,
                "project_name": project_name,
                "segment_count": len(conv_segments),
                "raw_markdown": combined_markdown,
                "metrics": {
                    "char_count": total_chars,
                    "word_count": total_words,
                    "line_count": combined_markdown.count("\n") + 1,
                    "estimated_tokens": total_chars // 4,
                    "tool_call_count": total_tools,
                },
            }
    return JSONResponse({"error": "project not found"}, status_code=404)


@app.get("/api/segments/{segment_id}")
def api_segment_detail(segment_id: str, provider: str = "claude"):
    """Return full segment data including raw markdown."""
    idx = get_index(provider)
    seg = idx["segments"].get(segment_id)
    if seg:
        return seg
    # Fallback: check all providers
    for pidx in INDEXES.values():
        seg = pidx["segments"].get(segment_id)
        if seg:
            return seg
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/segments/{segment_id}/export")
def api_segment_export(segment_id: str, provider: str = "claude"):
    """Return raw markdown for download/copy."""
    idx = get_index(provider)
    seg = idx["segments"].get(segment_id)
    if not seg:
        for pidx in INDEXES.values():
            seg = pidx["segments"].get(segment_id)
            if seg:
                break
    if seg:
        return JSONResponse({
            "filename": f"{seg['project_name']}_request_{seg['segment_index'] + 1}.md",
            "content": seg["raw_markdown"],
        })
    return JSONResponse({"error": "not found"}, status_code=404)


# ---------------------------------------------------------------------------
# Summary helpers — parse title from first line
# ---------------------------------------------------------------------------

# Each rollup chunk targets at most this many chars of input text. Sized
# conservatively to leave headroom inside the haiku model used by the
# watcher.
ROLLUP_CHUNK_TARGET = 80_000


def _parse_summary_file(content: str) -> dict:
    """Parse a summary file. First line is 'TITLE: ...' if present."""
    lines = content.strip().split("\n", 1)
    title = None
    body = content.strip()
    if lines and lines[0].startswith("TITLE: "):
        title = lines[0][7:].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
    return {"title": title, "summary": body}


def _summary_status(key: str) -> dict:
    """Read on-disk status for a single summary key (no orchestration)."""
    md_file = SUMMARIES_DIR / f"{key}.md"
    pending_file = SUMMARIES_DIR / f"{key}.pending"
    if md_file.exists():
        parsed = _parse_summary_file(md_file.read_text(encoding="utf-8"))
        return {"status": "ready", **parsed}
    if pending_file.exists():
        return {"status": "pending", "title": None, "summary": ""}
    return {"status": "none", "title": None, "summary": ""}


def _enqueue_summary_job(key: str, input_text: str) -> None:
    """Write .input + .pending so the watcher will produce key.md.

    No-op if the job already exists or has already completed.
    """
    md_file = SUMMARIES_DIR / f"{key}.md"
    pending_file = SUMMARIES_DIR / f"{key}.pending"
    if md_file.exists() or pending_file.exists():
        return
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    (SUMMARIES_DIR / f"{key}.input").write_text(input_text, encoding="utf-8")
    pending_file.write_text("", encoding="utf-8")


def _get_summary(key: str) -> dict:
    return _summary_status(key)


def _request_summary(key: str, markdown: str) -> dict:
    """Request a single-shot (per-segment) summary."""
    md_file = SUMMARIES_DIR / f"{key}.md"
    if md_file.exists():
        return _summary_status(key)
    _enqueue_summary_job(key, markdown)
    return {"status": "pending", "title": None, "summary": ""}


def _read_summary_body(key: str) -> Optional[str]:
    """Return a child summary as a single string (title prepended), or None
    if it isn't ready yet."""
    md_file = SUMMARIES_DIR / f"{key}.md"
    if not md_file.exists():
        return None
    parsed = _parse_summary_file(md_file.read_text(encoding="utf-8"))
    body = parsed["summary"]
    if parsed["title"]:
        return f"### {parsed['title']}\n\n{body}"
    return body


def _chunk_summaries(parts: list, target: int) -> list:
    """Greedily group string parts into chunks each <= target chars."""
    sep = "\n\n---\n\n"
    sep_len = len(sep)
    chunks = []
    current = []
    current_len = 0
    for part in parts:
        part_len = len(part)
        if part_len >= target:
            # Single oversized part — emit on its own.
            if current:
                chunks.append(sep.join(current))
                current = []
                current_len = 0
            chunks.append(part)
            continue
        added = part_len + (sep_len if current else 0)
        if current and current_len + added > target:
            chunks.append(sep.join(current))
            current = [part]
            current_len = part_len
        else:
            current.append(part)
            current_len += added
    if current:
        chunks.append(sep.join(current))
    return chunks


def _rollup_header(is_final: bool) -> str:
    if is_final:
        return (
            "The following are summaries of consecutive segments of a longer "
            "conversation, in chronological order. Synthesize them into ONE "
            "coherent summary covering the WHOLE conversation. Cover the full "
            "arc — what the user worked on across all segments, key decisions, "
            "and the final outcome. Do not focus only on the first or last "
            "segments.\n\n"
        )
    return (
        "The following are summaries of consecutive segments of a long "
        "conversation, in chronological order. Combine them into a single "
        "intermediate summary that preserves the chronological arc and key "
        "facts from every segment.\n\n"
    )


def _conv_state_path(key: str) -> Path:
    return SUMMARIES_DIR / f"{key}.state.json"


def _load_conv_state(key: str) -> Optional[dict]:
    p = _conv_state_path(key)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_conv_state(key: str, state: dict) -> None:
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    target = _conv_state_path(key)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    os.replace(tmp, target)


def _conv_progress(state: Optional[dict]) -> dict:
    """Snapshot of how far along the hierarchical state machine is. The
    frontend reads this to (a) reset its watcher-dead timeout on every
    observable advance and (b) show a useful loading message."""
    if state is None:
        return {"phase": "starting", "done": 0, "total": 0, "level": 0}
    phase = state.get("phase")
    if phase == "segments":
        seg_keys = state.get("segment_keys", [])
        done = sum(1 for k in seg_keys if (SUMMARIES_DIR / f"{k}.md").exists())
        return {"phase": "segments", "done": done, "total": len(seg_keys), "level": 0}
    if phase == "rollup":
        chunk_keys = state.get("current_chunk_keys", [])
        done = sum(1 for k in chunk_keys if (SUMMARIES_DIR / f"{k}.md").exists())
        return {
            "phase": "rollup",
            "done": done,
            "total": len(chunk_keys),
            "level": state.get("rollup_level", 0),
        }
    return {"phase": phase or "unknown", "done": 0, "total": 0, "level": 0}


def _conv_pending(state: Optional[dict]) -> dict:
    return {
        "status": "pending",
        "title": None,
        "summary": "",
        "progress": _conv_progress(state),
    }


def _delete_conv_artifacts(key: str) -> None:
    """Remove a conv summary plus every helper file it spawned."""
    state = _load_conv_state(key)
    if state:
        for chunk_key in state.get("all_chunk_keys", []):
            for ext in (".md", ".pending", ".input"):
                f = SUMMARIES_DIR / f"{chunk_key}{ext}"
                if f.exists():
                    f.unlink()
    for ext in (".md", ".pending", ".input", ".state.json"):
        f = SUMMARIES_DIR / f"{key}{ext}"
        if f.exists():
            f.unlink()


def _invalidate_dependent_conv_summaries(segment_key: str) -> None:
    """When a segment summary is regenerated, drop any conv summary that
    used it so it gets rebuilt on next request."""
    if not SUMMARIES_DIR.exists():
        return
    for state_file in SUMMARIES_DIR.glob("conv_*.state.json"):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if segment_key in state.get("segment_keys", []):
            conv_key = state_file.name[: -len(".state.json")]
            _delete_conv_artifacts(conv_key)


def _start_rollup_level(key: str, state: dict, child_summaries: list) -> dict:
    """Build the next rollup level: chunk child summaries, enqueue jobs."""
    chunks = _chunk_summaries(child_summaries, ROLLUP_CHUNK_TARGET)
    next_level = state.get("rollup_level", -1) + 1 if state.get("phase") == "rollup" else 0
    is_final = len(chunks) == 1
    header = _rollup_header(is_final)
    new_chunk_keys = []
    for idx, chunk_text in enumerate(chunks):
        chunk_key = f"{key}__r{next_level}_{idx}"
        new_chunk_keys.append(chunk_key)
        _enqueue_summary_job(chunk_key, header + chunk_text)
    state["phase"] = "rollup"
    state["rollup_level"] = next_level
    state["current_chunk_keys"] = new_chunk_keys
    state.setdefault("all_chunk_keys", []).extend(new_chunk_keys)
    _save_conv_state(key, state)
    return _conv_pending(state)


def _advance_conv_summary(key: str, segments: list) -> dict:
    """Drive the conversation summary state machine forward by one step.

    Phases:
      (none)    initial — enqueue per-segment summary jobs
      segments  waiting for per-segment summaries to complete
      rollup    waiting for the current rollup level to complete; advances
                to the next level until only one chunk remains, which
                becomes the conv summary

    Per-segment summaries are always generated first so individual requests
    in the UI also get cached summaries as a side effect of summarizing the
    whole conversation.
    """
    md_file = SUMMARIES_DIR / f"{key}.md"
    pending_file = SUMMARIES_DIR / f"{key}.pending"

    if md_file.exists():
        if pending_file.exists():
            pending_file.unlink()
        return _summary_status(key)

    state = _load_conv_state(key)

    # First call: enqueue per-segment summaries.
    if state is None:
        SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
        seg_keys = [seg["id"] for seg in segments]
        state = {
            "phase": "segments",
            "segment_keys": seg_keys,
            "rollup_level": -1,
            "current_chunk_keys": [],
            "all_chunk_keys": [],
        }
        _save_conv_state(key, state)
        pending_file.write_text("", encoding="utf-8")
        for seg in segments:
            _request_summary(seg["id"], seg["raw_markdown"])
        return _conv_pending(state)

    phase = state.get("phase")

    if phase == "segments":
        seg_summaries = []
        all_ready = True
        seg_by_id = {seg["id"]: seg for seg in segments}
        for sk in state["segment_keys"]:
            body = _read_summary_body(sk)
            if body is None:
                all_ready = False
                if not (SUMMARIES_DIR / f"{sk}.pending").exists():
                    seg = seg_by_id.get(sk)
                    if seg is not None:
                        _request_summary(sk, seg["raw_markdown"])
            else:
                seg_summaries.append(body)
        if not all_ready:
            return _conv_pending(state)
        # Fast path: a single-segment conversation needs no rollup — the
        # segment summary IS the conversation summary.
        if len(state["segment_keys"]) == 1:
            only_seg_key = state["segment_keys"][0]
            shutil.copy2(SUMMARIES_DIR / f"{only_seg_key}.md", md_file)
            if pending_file.exists():
                pending_file.unlink()
            return _summary_status(key)
        return _start_rollup_level(key, state, seg_summaries)

    if phase == "rollup":
        chunk_keys = state.get("current_chunk_keys", [])
        chunk_summaries = []
        all_ready = True
        for ck in chunk_keys:
            body = _read_summary_body(ck)
            if body is None:
                all_ready = False
            else:
                chunk_summaries.append(body)
        if not all_ready:
            return _conv_pending(state)

        if len(chunk_keys) == 1:
            shutil.copy2(SUMMARIES_DIR / f"{chunk_keys[0]}.md", md_file)
            if pending_file.exists():
                pending_file.unlink()
            return _summary_status(key)

        return _start_rollup_level(key, state, chunk_summaries)

    return _conv_pending(state)


def _drive_conv_summary(project_name: str, conversation_id: str, provider: str):
    """Look up a conversation, then advance its summary state machine.

    Returns a status dict on success, or None when the conversation can't be
    found (caller should return 404).
    """
    key = f"conv_{project_name}_{conversation_id}"
    md_file = SUMMARIES_DIR / f"{key}.md"
    if md_file.exists():
        pf = SUMMARIES_DIR / f"{key}.pending"
        if pf.exists():
            pf.unlink()
        return _summary_status(key)

    idx = get_index(provider)
    for p in idx["projects"]:
        if p["name"] == project_name:
            conv_segments = [
                idx["segments"][s["id"]]
                for s in p["segments"]
                if s.get("conversation_id") == conversation_id
                and s.get("project_name") == project_name
                and s["id"] in idx["segments"]
            ]
            if not conv_segments:
                return None
            return _advance_conv_summary(key, conv_segments)
    return None


# ---------------------------------------------------------------------------
# Summary API — specific routes BEFORE wildcard {segment_id}
# ---------------------------------------------------------------------------
@app.get("/api/summary/titles")
def api_summary_titles():
    """Return all cached summary titles as a map of {key: title}.
    Used by the request list to replace default headings."""
    titles = {}
    if not SUMMARIES_DIR.exists():
        return titles
    for md_file in SUMMARIES_DIR.glob("*.md"):
        key = md_file.stem
        # Skip internal hierarchical-summary helper artifacts (single-shot
        # wrappers and rollup chunks). They use double underscores in the
        # key and aren't exposed to the UI.
        if "__" in key:
            continue
        try:
            first_line = md_file.read_text(encoding="utf-8").split("\n", 1)[0]
            if first_line.startswith("TITLE: "):
                titles[key] = first_line[7:].strip()
        except (OSError, UnicodeDecodeError):
            pass
    return titles


@app.get("/api/summary/conversation/{project_name}/{conversation_id}")
def api_conv_summary_get(project_name: str, conversation_id: str):
    """Check if a summary exists for a conversation. Polling this endpoint
    also drives the hierarchical state machine forward."""
    result = _drive_conv_summary(project_name, conversation_id, "claude")
    if result is None:
        # No state yet — fall back to a plain status read so we don't 404
        # before the first POST has happened.
        key = f"conv_{project_name}_{conversation_id}"
        return _summary_status(key)
    return result


@app.post("/api/summary/conversation/{project_name}/{conversation_id}")
def api_conv_summary_request(project_name: str, conversation_id: str, provider: str = "claude"):
    """Request a hierarchical summary for an entire conversation."""
    result = _drive_conv_summary(project_name, conversation_id, provider)
    if result is None:
        return JSONResponse({"error": "conversation not found"}, status_code=404)
    return result


@app.delete("/api/summary/{segment_id}")
def api_summary_delete(segment_id: str):
    """Delete a cached summary so it can be regenerated."""
    if segment_id.startswith("conv_"):
        _delete_conv_artifacts(segment_id)
    else:
        for ext in (".md", ".pending", ".input"):
            f = SUMMARIES_DIR / f"{segment_id}{ext}"
            if f.exists():
                f.unlink()
        # Any conv summary that depended on this segment is now stale.
        _invalidate_dependent_conv_summaries(segment_id)
    return {"ok": True}


@app.get("/api/summary/{segment_id}")
def api_summary_get(segment_id: str):
    """Check if a summary exists for a segment."""
    return _summary_status(segment_id)


@app.post("/api/summary/{segment_id}")
def api_summary_request(segment_id: str, provider: str = "claude"):
    """Request a summary for a segment."""
    idx = get_index(provider)
    seg = idx["segments"].get(segment_id)
    if not seg:
        # Fallback: check all providers
        for pidx in INDEXES.values():
            seg = pidx["segments"].get(segment_id)
            if seg:
                break
    if not seg:
        return JSONResponse({"error": "segment not found"}, status_code=404)
    return _request_summary(segment_id, seg["raw_markdown"])


@app.get("/api/search")
def api_search(q: Optional[str] = Query(None), show_hidden: bool = False, provider: str = "claude"):
    """Search across all segments."""
    if not q or len(q.strip()) < 2:
        return []

    idx = get_index(provider)
    st = browser_state.get_state()
    query = q.strip().lower()
    results = []
    limit = 100

    for seg_id, seg in idx["segments"].items():
        if len(results) >= limit:
            break
        if not show_hidden and browser_state.is_segment_hidden(st, seg):
            continue
        if query in seg.get("preview", "").lower() or query in seg.get("raw_markdown", "").lower():
            results.append({
                "id": seg["id"],
                "project_name": seg["project_name"],
                "segment_index": seg["segment_index"],
                "preview": seg["preview"],
                "timestamp": seg["timestamp"],
                "conversation_id": seg["conversation_id"],
                "metrics": seg["metrics"],
                "hidden": browser_state.is_segment_hidden(st, seg),
            })

    return results


@app.get("/api/stats")
def api_stats(provider: str = "claude"):
    """Return global statistics."""
    idx = get_index(provider)
    st = browser_state.get_state()
    total_chars = sum(s["metrics"]["char_count"] for s in idx["segments"].values())
    total_words = sum(s["metrics"]["word_count"] for s in idx["segments"].values())
    total_tool_calls = sum(s["metrics"]["tool_call_count"] for s in idx["segments"].values())
    counts = browser_state.hidden_counts(st)

    # Monthly breakdown
    monthly: dict[str, dict] = {}
    for seg in idx["segments"].values():
        ts = seg.get("timestamp")
        if ts:
            month = ts[:7]  # "2026-03"
            if month not in monthly:
                monthly[month] = {"tokens": 0, "requests": 0}
            monthly[month]["tokens"] += seg["metrics"]["estimated_tokens"]
            monthly[month]["requests"] += 1

    est_tokens = total_chars // 4
    monthly_sorted = {m: d for m, d in sorted(monthly.items())}

    return {
        "total_projects": len(idx["projects"]),
        "total_segments": len(idx["segments"]),
        "total_chars": total_chars,
        "total_words": total_words,
        "total_tool_calls": total_tool_calls,
        "estimated_tokens": est_tokens,
        "monthly": monthly_sorted,
        "watch_interval": WATCH_INTERVAL,
        "hidden": counts,
    }


@app.post("/api/update")
def api_update():
    """Run the full export pipeline: sync, convert, re-index."""
    try:
        result = run_export_pipeline()
        status_code = 200 if result["success"] else 500
        return JSONResponse(result, status_code=status_code)
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e), "log": traceback.format_exc().split("\n")},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Hide / Restore API
# ---------------------------------------------------------------------------
@app.post("/api/hide/segment/{segment_id}")
def api_hide_segment(segment_id: str):
    st = browser_state.hide_segment(segment_id)
    return {"ok": True, "hidden": browser_state.hidden_counts(st)}


@app.post("/api/restore/segment/{segment_id}")
def api_restore_segment(segment_id: str):
    st = browser_state.restore_segment(segment_id)
    return {"ok": True, "hidden": browser_state.hidden_counts(st)}


@app.post("/api/hide/conversation/{project_name}/{conversation_id}")
def api_hide_conversation(project_name: str, conversation_id: str):
    st = browser_state.hide_conversation(project_name, conversation_id)
    return {"ok": True, "hidden": browser_state.hidden_counts(st)}


@app.post("/api/restore/conversation/{project_name}/{conversation_id}")
def api_restore_conversation(project_name: str, conversation_id: str):
    st = browser_state.restore_conversation(project_name, conversation_id)
    return {"ok": True, "hidden": browser_state.hidden_counts(st)}


@app.post("/api/hide/project/{project_name}")
def api_hide_project(project_name: str):
    st = browser_state.hide_project(project_name)
    return {"ok": True, "hidden": browser_state.hidden_counts(st)}


@app.post("/api/restore/project/{project_name}")
def api_restore_project(project_name: str):
    st = browser_state.restore_project(project_name)
    return {"ok": True, "hidden": browser_state.hidden_counts(st)}


@app.post("/api/restore/all")
def api_restore_all():
    st = browser_state.restore_all()
    return {"ok": True, "hidden": browser_state.hidden_counts(st)}


@app.get("/api/hidden")
def api_hidden():
    """Return full hidden state for the trash view."""
    st = browser_state.get_state()
    # Enrich with previews for hidden segments
    hidden_segments = []
    for seg_id, hidden_at in st.get("hidden_segments", {}).items():
        seg = None
        for pidx in INDEXES.values():
            seg = pidx["segments"].get(seg_id)
            if seg:
                break
        if seg:
            hidden_segments.append({
                "id": seg_id,
                "preview": seg["preview"],
                "project_name": seg["project_name"],
                "conversation_id": seg.get("conversation_id"),
                "hidden_at": hidden_at,
            })
    return {
        "segments": hidden_segments,
        "conversations": [
            {"key": k, "hidden_at": v}
            for k, v in st.get("hidden_conversations", {}).items()
        ],
        "projects": [
            {"name": k, "hidden_at": v}
            for k, v in st.get("hidden_projects", {}).items()
        ],
    }


# ---------------------------------------------------------------------------
# Serve React static build (production / Docker)
# ---------------------------------------------------------------------------
static_path = Path(STATIC_DIR)
if static_path.exists() and (static_path / "index.html").exists():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    if (static_path / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(static_path / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = static_path / full_path
        # Guard against path traversal (defense-in-depth)
        if not str(file_path.resolve()).startswith(str(static_path.resolve())):
            return FileResponse(str(static_path / "index.html"))
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(static_path / "index.html"))
