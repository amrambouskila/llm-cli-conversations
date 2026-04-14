from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Segment, Session

SUMMARIES_DIR = Path(os.environ.get("SUMMARY_DIR", "/data/state/summaries"))

ROLLUP_CHUNK_TARGET = 80_000


class SummaryService:
    """Owns the filesystem-backed summary state machine.

    The host-side watcher (launched by the launcher scripts) polls
    ``SUMMARIES_DIR`` for ``*.pending`` files, invokes the Claude CLI to
    produce ``*.md`` results, and deletes the pending marker. This service
    writes the pending markers, reads back the results, and orchestrates the
    hierarchical conversation rollup that chunks long conversations into
    cascading summary passes.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Segment summaries (one-shot)
    # ------------------------------------------------------------------

    def get_segment_summary(self, segment_id: str) -> dict:
        return _summary_status(segment_id)

    async def request_segment_summary(self, segment_id: str) -> dict | None:
        result = await self.db.execute(select(Segment).where(Segment.id == segment_id))
        seg = result.scalar_one_or_none()
        if not seg:
            return None
        return _request_summary(segment_id, seg.raw_text or "")

    def delete_summary(self, segment_id: str) -> None:
        if segment_id.startswith("conv_"):
            _delete_conv_artifacts(segment_id)
            return
        for ext in (".md", ".pending", ".input"):
            f = SUMMARIES_DIR / f"{segment_id}{ext}"
            if f.exists():
                f.unlink()
        _invalidate_dependent_conv_summaries(segment_id)

    # ------------------------------------------------------------------
    # Conversation summaries (hierarchical rollup)
    # ------------------------------------------------------------------

    async def get_conversation_summary(
        self,
        project_name: str,
        conversation_id: str,
        provider: str = "claude",
    ) -> dict | None:
        result = await self._drive_conv_summary(project_name, conversation_id, provider)
        if result is None:
            key = f"conv_{project_name}_{conversation_id}"
            return _summary_status(key)
        return result

    async def request_conversation_summary(
        self,
        project_name: str,
        conversation_id: str,
        provider: str = "claude",
    ) -> dict | None:
        return await self._drive_conv_summary(project_name, conversation_id, provider)

    async def _drive_conv_summary(
        self,
        project_name: str,
        conversation_id: str,
        provider: str,
    ) -> dict | None:
        key = f"conv_{project_name}_{conversation_id}"
        md_file = SUMMARIES_DIR / f"{key}.md"
        if md_file.exists():
            pending_file = SUMMARIES_DIR / f"{key}.pending"
            if pending_file.exists():
                pending_file.unlink()
            return _summary_status(key)

        result = await self.db.execute(
            select(Segment)
            .join(Session)
            .where(
                Session.conversation_id == conversation_id,
                Session.project == project_name,
                Session.provider == provider,
            )
            .order_by(Segment.segment_index)
        )
        db_segments = result.scalars().all()
        if not db_segments:
            return None
        conv_segments = [
            {"id": seg.id, "raw_markdown": seg.raw_text or ""} for seg in db_segments
        ]
        return _advance_conv_summary(key, conv_segments)

    # ------------------------------------------------------------------
    # Bulk title lookup (used by the request-list sidebar)
    # ------------------------------------------------------------------

    @staticmethod
    def get_all_titles() -> dict[str, str]:
        titles: dict[str, str] = {}
        if not SUMMARIES_DIR.exists():
            return titles
        for md_file in SUMMARIES_DIR.glob("*.md"):
            key = md_file.stem
            if "__" in key:
                continue
            try:
                first_line = md_file.read_text(encoding="utf-8").split("\n", 1)[0]
                if first_line.startswith("TITLE: "):
                    titles[key] = first_line[7:].strip()
            except (OSError, UnicodeDecodeError):
                pass
        return titles


# ---------------------------------------------------------------------------
# Filesystem helpers — kept module-level because they're pure functions of the
# state dir's contents. Splitting them into methods would just force the service
# constructor everywhere without improving testability.
# ---------------------------------------------------------------------------


def _parse_summary_file(content: str) -> dict:
    lines = content.strip().split("\n", 1)
    title = None
    body = content.strip()
    if lines and lines[0].startswith("TITLE: "):
        title = lines[0][7:].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
    return {"title": title, "summary": body}


def _summary_status(key: str) -> dict:
    md_file = SUMMARIES_DIR / f"{key}.md"
    pending_file = SUMMARIES_DIR / f"{key}.pending"
    if md_file.exists():
        parsed = _parse_summary_file(md_file.read_text(encoding="utf-8"))
        return {"status": "ready", **parsed}
    if pending_file.exists():
        return {"status": "pending", "title": None, "summary": ""}
    return {"status": "none", "title": None, "summary": ""}


def _enqueue_summary_job(key: str, input_text: str) -> None:
    md_file = SUMMARIES_DIR / f"{key}.md"
    pending_file = SUMMARIES_DIR / f"{key}.pending"
    if md_file.exists() or pending_file.exists():
        return
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    (SUMMARIES_DIR / f"{key}.input").write_text(input_text, encoding="utf-8")
    pending_file.write_text("", encoding="utf-8")


def _request_summary(key: str, markdown: str) -> dict:
    md_file = SUMMARIES_DIR / f"{key}.md"
    if md_file.exists():
        return _summary_status(key)
    _enqueue_summary_job(key, markdown)
    return {"status": "pending", "title": None, "summary": ""}


# Back-compat alias — older tests called `_get_summary(key)`.
_get_summary = _summary_status


def _read_summary_body(key: str) -> str | None:
    md_file = SUMMARIES_DIR / f"{key}.md"
    if not md_file.exists():
        return None
    parsed = _parse_summary_file(md_file.read_text(encoding="utf-8"))
    body = parsed["summary"]
    if parsed["title"]:
        return f"### {parsed['title']}\n\n{body}"
    return body


def _chunk_summaries(parts: list, target: int) -> list:
    sep = "\n\n---\n\n"
    sep_len = len(sep)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for part in parts:
        part_len = len(part)
        if part_len >= target:
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


def _load_conv_state(key: str) -> dict | None:
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


def _conv_progress(state: dict | None) -> dict:
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


def _conv_pending(state: dict | None) -> dict:
    return {
        "status": "pending",
        "title": None,
        "summary": "",
        "progress": _conv_progress(state),
    }


def _delete_conv_artifacts(key: str) -> None:
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
    chunks = _chunk_summaries(child_summaries, ROLLUP_CHUNK_TARGET)
    next_level = state.get("rollup_level", -1) + 1 if state.get("phase") == "rollup" else 0
    is_final = len(chunks) == 1
    header = _rollup_header(is_final)
    new_chunk_keys: list[str] = []
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
    md_file = SUMMARIES_DIR / f"{key}.md"
    pending_file = SUMMARIES_DIR / f"{key}.pending"

    if md_file.exists():
        if pending_file.exists():
            pending_file.unlink()
        return _summary_status(key)

    state = _load_conv_state(key)

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
        seg_summaries: list[str] = []
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
        if len(state["segment_keys"]) == 1:
            only_seg_key = state["segment_keys"][0]
            shutil.copy2(SUMMARIES_DIR / f"{only_seg_key}.md", md_file)
            if pending_file.exists():
                pending_file.unlink()
            return _summary_status(key)
        return _start_rollup_level(key, state, seg_summaries)

    if phase == "rollup":
        chunk_keys = state.get("current_chunk_keys", [])
        chunk_summaries: list[str] = []
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
