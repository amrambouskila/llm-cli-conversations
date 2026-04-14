"""Tests for the summary orchestration state machine and API routes.

Helpers (``_parse_summary_file``, ``_advance_conv_summary``, etc.) and
``SUMMARIES_DIR`` moved from ``routes/summaries.py`` to
``services/summary_service.py`` during the Phase 7.1 OOP refactor.
"""
from __future__ import annotations

import json

import pytest

from services import summary_service as summaries_mod


@pytest.fixture(autouse=True)
def _point_summary_dir_to_tmp(tmp_path, monkeypatch):
    """Redirect SUMMARIES_DIR to a fresh tmp_path so tests don't pollute /data/state/summaries."""
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_parse_summary_file_with_title():
    content = "TITLE: Docker auth\n\nbody text"
    parsed = summaries_mod._parse_summary_file(content)
    assert parsed["title"] == "Docker auth"
    assert parsed["summary"] == "body text"


def test_parse_summary_file_no_title():
    parsed = summaries_mod._parse_summary_file("just body")
    assert parsed["title"] is None
    assert parsed["summary"] == "just body"


def test_parse_summary_file_title_only():
    parsed = summaries_mod._parse_summary_file("TITLE: Only")
    assert parsed["title"] == "Only"
    assert parsed["summary"] == ""


def test_summary_status_none(tmp_path):
    status = summaries_mod._summary_status("missing")
    assert status["status"] == "none"


def test_summary_status_pending(tmp_path):
    (tmp_path / "k.pending").write_text("", encoding="utf-8")
    status = summaries_mod._summary_status("k")
    assert status["status"] == "pending"


def test_summary_status_ready(tmp_path):
    (tmp_path / "k.md").write_text("TITLE: Hello\n\nbody", encoding="utf-8")
    status = summaries_mod._summary_status("k")
    assert status["status"] == "ready"
    assert status["title"] == "Hello"
    assert status["summary"] == "body"


def test_enqueue_summary_job_creates_files(tmp_path):
    summaries_mod._enqueue_summary_job("key1", "text input")
    assert (tmp_path / "key1.input").read_text(encoding="utf-8") == "text input"
    assert (tmp_path / "key1.pending").exists()


def test_enqueue_summary_job_skips_if_exists(tmp_path):
    (tmp_path / "k.md").write_text("x", encoding="utf-8")
    summaries_mod._enqueue_summary_job("k", "ignored")
    assert not (tmp_path / "k.input").exists()


def test_enqueue_summary_job_skips_if_pending(tmp_path):
    (tmp_path / "k.pending").write_text("", encoding="utf-8")
    summaries_mod._enqueue_summary_job("k", "ignored")
    assert not (tmp_path / "k.input").exists()


def test_get_summary_wraps_status(tmp_path):
    (tmp_path / "k.md").write_text("body", encoding="utf-8")
    r = summaries_mod._get_summary("k")
    assert r["status"] == "ready"


def test_request_summary_when_ready(tmp_path):
    (tmp_path / "k.md").write_text("body", encoding="utf-8")
    r = summaries_mod._request_summary("k", "markdown")
    assert r["status"] == "ready"


def test_request_summary_enqueues(tmp_path):
    r = summaries_mod._request_summary("k", "markdown body")
    assert r["status"] == "pending"
    assert (tmp_path / "k.input").exists()


def test_read_summary_body_missing(tmp_path):
    assert summaries_mod._read_summary_body("nope") is None


def test_read_summary_body_with_title(tmp_path):
    (tmp_path / "k.md").write_text("TITLE: T\n\nbody", encoding="utf-8")
    body = summaries_mod._read_summary_body("k")
    assert body.startswith("### T")
    assert "body" in body


def test_read_summary_body_no_title(tmp_path):
    (tmp_path / "k.md").write_text("just body", encoding="utf-8")
    assert summaries_mod._read_summary_body("k") == "just body"


def test_chunk_summaries_small_stays_single():
    parts = ["a", "b", "c"]
    chunks = summaries_mod._chunk_summaries(parts, target=1000)
    assert len(chunks) == 1


def test_chunk_summaries_oversized_part_gets_own_chunk():
    # One part exceeds target; gets its own chunk
    big = "x" * 100
    parts = ["a", big, "b"]
    chunks = summaries_mod._chunk_summaries(parts, target=50)
    assert big in chunks


def test_chunk_summaries_split_when_exceeding():
    parts = ["aaaa", "bbbb", "cccc"]
    chunks = summaries_mod._chunk_summaries(parts, target=10)
    # Each ~4 chars + sep(7) > 10, so they split
    assert len(chunks) >= 2


def test_rollup_header_intermediate_vs_final():
    inter = summaries_mod._rollup_header(is_final=False)
    final = summaries_mod._rollup_header(is_final=True)
    assert "intermediate" in inter
    assert "ONE" in final


def test_conv_state_roundtrip(tmp_path):
    state = {"phase": "segments", "segment_keys": ["a", "b"]}
    summaries_mod._save_conv_state("conv_x", state)
    loaded = summaries_mod._load_conv_state("conv_x")
    assert loaded == state


def test_load_conv_state_missing(tmp_path):
    assert summaries_mod._load_conv_state("nope") is None


def test_load_conv_state_corrupt(tmp_path):
    (tmp_path / "conv_bad.state.json").write_text("{not json", encoding="utf-8")
    assert summaries_mod._load_conv_state("conv_bad") is None


def test_conv_progress_none():
    p = summaries_mod._conv_progress(None)
    assert p["phase"] == "starting"


def test_conv_progress_segments(tmp_path):
    (tmp_path / "a.md").write_text("x", encoding="utf-8")
    state = {"phase": "segments", "segment_keys": ["a", "b"]}
    p = summaries_mod._conv_progress(state)
    assert p["phase"] == "segments"
    assert p["done"] == 1
    assert p["total"] == 2


def test_conv_progress_rollup(tmp_path):
    state = {"phase": "rollup", "current_chunk_keys": ["c1", "c2"], "rollup_level": 1}
    p = summaries_mod._conv_progress(state)
    assert p["phase"] == "rollup"
    assert p["total"] == 2
    assert p["level"] == 1


def test_conv_progress_unknown_phase():
    p = summaries_mod._conv_progress({"phase": "weird"})
    assert p["phase"] == "weird"


def test_conv_pending_shape():
    r = summaries_mod._conv_pending({"phase": "segments", "segment_keys": []})
    assert r["status"] == "pending"
    assert "progress" in r


def test_delete_conv_artifacts(tmp_path):
    # Create conv + chunk files
    state = {"all_chunk_keys": ["conv_x__r0_0"]}
    (tmp_path / "conv_x.state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "conv_x.md").write_text("x", encoding="utf-8")
    (tmp_path / "conv_x.pending").write_text("", encoding="utf-8")
    (tmp_path / "conv_x__r0_0.md").write_text("x", encoding="utf-8")
    (tmp_path / "conv_x__r0_0.input").write_text("x", encoding="utf-8")

    summaries_mod._delete_conv_artifacts("conv_x")
    assert not (tmp_path / "conv_x.md").exists()
    assert not (tmp_path / "conv_x.state.json").exists()
    assert not (tmp_path / "conv_x__r0_0.md").exists()


def test_invalidate_dependent_conv_summaries(tmp_path):
    state = {"segment_keys": ["seg-1", "seg-2"]}
    (tmp_path / "conv_x.state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "conv_x.md").write_text("x", encoding="utf-8")

    summaries_mod._invalidate_dependent_conv_summaries("seg-1")
    assert not (tmp_path / "conv_x.md").exists()
    assert not (tmp_path / "conv_x.state.json").exists()


def test_invalidate_dependent_conv_summaries_no_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path / "nope")
    # Should not raise
    summaries_mod._invalidate_dependent_conv_summaries("seg-1")


def test_invalidate_dependent_corrupt_state_file(tmp_path):
    (tmp_path / "conv_bad.state.json").write_text("nope", encoding="utf-8")
    (tmp_path / "conv_bad.md").write_text("x", encoding="utf-8")
    summaries_mod._invalidate_dependent_conv_summaries("seg-1")
    # Corrupt state is skipped, conv_bad.md remains
    assert (tmp_path / "conv_bad.md").exists()


def test_invalidate_dependent_no_match(tmp_path):
    state = {"segment_keys": ["seg-9"]}
    (tmp_path / "conv_y.state.json").write_text(json.dumps(state), encoding="utf-8")
    (tmp_path / "conv_y.md").write_text("x", encoding="utf-8")
    summaries_mod._invalidate_dependent_conv_summaries("seg-1")
    assert (tmp_path / "conv_y.md").exists()


# ---------------------------------------------------------------------------
# _advance_conv_summary state machine
# ---------------------------------------------------------------------------

def test_advance_conv_summary_ready_returns_status(tmp_path):
    (tmp_path / "conv_k.md").write_text("TITLE: Done\n\nbody", encoding="utf-8")
    (tmp_path / "conv_k.pending").write_text("", encoding="utf-8")
    r = summaries_mod._advance_conv_summary("conv_k", [])
    assert r["status"] == "ready"
    # pending cleanup
    assert not (tmp_path / "conv_k.pending").exists()


def test_advance_conv_summary_starts_segments(tmp_path):
    segs = [{"id": "seg-1", "raw_markdown": "hello"}, {"id": "seg-2", "raw_markdown": "world"}]
    r = summaries_mod._advance_conv_summary("conv_k", segs)
    assert r["status"] == "pending"
    # Enqueued input files for each seg
    assert (tmp_path / "seg-1.input").exists()
    assert (tmp_path / "seg-2.input").exists()
    # State saved
    state = summaries_mod._load_conv_state("conv_k")
    assert state["phase"] == "segments"


def test_advance_conv_summary_segments_not_all_ready(tmp_path):
    segs = [{"id": "seg-1", "raw_markdown": "hi"}]
    summaries_mod._advance_conv_summary("conv_k", segs)
    # Call again without seg-1.md ready
    r = summaries_mod._advance_conv_summary("conv_k", segs)
    assert r["status"] == "pending"


def test_advance_conv_summary_single_segment_copies(tmp_path):
    segs = [{"id": "seg-1", "raw_markdown": "hi"}]
    summaries_mod._advance_conv_summary("conv_k", segs)
    # Simulate segment summary ready
    (tmp_path / "seg-1.md").write_text("TITLE: Single\n\ndone", encoding="utf-8")
    r = summaries_mod._advance_conv_summary("conv_k", segs)
    assert r["status"] == "ready"
    assert r["title"] == "Single"


def test_advance_conv_summary_multi_segment_starts_rollup(tmp_path):
    segs = [
        {"id": "seg-1", "raw_markdown": "hi"},
        {"id": "seg-2", "raw_markdown": "there"},
    ]
    summaries_mod._advance_conv_summary("conv_k", segs)
    # Both seg summaries ready
    (tmp_path / "seg-1.md").write_text("TITLE: A\n\na-body", encoding="utf-8")
    (tmp_path / "seg-2.md").write_text("TITLE: B\n\nb-body", encoding="utf-8")
    r = summaries_mod._advance_conv_summary("conv_k", segs)
    assert r["status"] == "pending"
    state = summaries_mod._load_conv_state("conv_k")
    assert state["phase"] == "rollup"
    assert len(state["current_chunk_keys"]) >= 1


def test_advance_conv_summary_rollup_final_copies(tmp_path):
    # Set up state directly in rollup phase with one chunk
    state = {
        "phase": "rollup",
        "segment_keys": ["seg-1"],
        "rollup_level": 0,
        "current_chunk_keys": ["conv_k__r0_0"],
        "all_chunk_keys": ["conv_k__r0_0"],
    }
    summaries_mod._save_conv_state("conv_k", state)
    (tmp_path / "conv_k.pending").write_text("", encoding="utf-8")
    (tmp_path / "conv_k__r0_0.md").write_text("TITLE: Final\n\nall", encoding="utf-8")

    r = summaries_mod._advance_conv_summary("conv_k", [])
    assert r["status"] == "ready"
    assert r["title"] == "Final"


def test_advance_conv_summary_rollup_not_ready(tmp_path):
    state = {
        "phase": "rollup",
        "segment_keys": [],
        "rollup_level": 0,
        "current_chunk_keys": ["conv_k__r0_0", "conv_k__r0_1"],
        "all_chunk_keys": ["conv_k__r0_0", "conv_k__r0_1"],
    }
    summaries_mod._save_conv_state("conv_k", state)
    r = summaries_mod._advance_conv_summary("conv_k", [])
    assert r["status"] == "pending"


def test_advance_conv_summary_rollup_cascades(tmp_path):
    state = {
        "phase": "rollup",
        "segment_keys": [],
        "rollup_level": 0,
        "current_chunk_keys": ["conv_k__r0_0", "conv_k__r0_1"],
        "all_chunk_keys": ["conv_k__r0_0", "conv_k__r0_1"],
    }
    summaries_mod._save_conv_state("conv_k", state)
    (tmp_path / "conv_k__r0_0.md").write_text("TITLE: C1\n\n" + ("x" * 50000), encoding="utf-8")
    (tmp_path / "conv_k__r0_1.md").write_text("TITLE: C2\n\n" + ("y" * 50000), encoding="utf-8")
    r = summaries_mod._advance_conv_summary("conv_k", [])
    assert r["status"] == "pending"
    state2 = summaries_mod._load_conv_state("conv_k")
    assert state2["rollup_level"] == 1


def test_advance_conv_summary_unknown_phase(tmp_path):
    state = {"phase": "weird", "segment_keys": [], "all_chunk_keys": []}
    summaries_mod._save_conv_state("conv_k", state)
    r = summaries_mod._advance_conv_summary("conv_k", [])
    assert r["status"] == "pending"


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

async def test_api_summary_titles_empty(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path / "empty")
    r = await api_client.get("/api/summary/titles")
    assert r.status_code == 200
    assert r.json() == {}


async def test_api_summary_titles_reads_md(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    (tmp_path / "seg-1.md").write_text("TITLE: Hello\n\nbody", encoding="utf-8")
    (tmp_path / "seg-no-title.md").write_text("no title here", encoding="utf-8")
    (tmp_path / "chunk__r0_0.md").write_text("TITLE: Chunk\n\nx", encoding="utf-8")

    r = await api_client.get("/api/summary/titles")
    data = r.json()
    assert data.get("seg-1") == "Hello"
    # no-title file: no TITLE: prefix, so absent
    assert "seg-no-title" not in data
    # chunk (has "__") excluded
    assert "chunk__r0_0" not in data


async def test_api_summary_get_none(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    r = await api_client.get("/api/summary/seg-never-summarized")
    assert r.status_code == 200
    assert r.json()["status"] == "none"


async def test_api_summary_get_ready(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    (tmp_path / "seg-1.md").write_text("TITLE: Done\n\nx", encoding="utf-8")
    r = await api_client.get("/api/summary/seg-1")
    assert r.json()["status"] == "ready"


async def test_api_summary_request_404_unknown_segment(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    r = await api_client.post("/api/summary/does-not-exist")
    assert r.status_code == 404


async def test_api_summary_request_enqueues(seed_sessions, api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    r = await api_client.post("/api/summary/seg-1a")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert (tmp_path / "seg-1a.input").exists()


async def test_api_summary_delete_segment_removes_files(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    (tmp_path / "seg-1.md").write_text("x", encoding="utf-8")
    (tmp_path / "seg-1.input").write_text("x", encoding="utf-8")
    r = await api_client.delete("/api/summary/seg-1")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert not (tmp_path / "seg-1.md").exists()


async def test_api_summary_delete_conv_variant(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    (tmp_path / "conv_x.md").write_text("x", encoding="utf-8")
    (tmp_path / "conv_x.state.json").write_text(json.dumps({"all_chunk_keys": []}), encoding="utf-8")
    r = await api_client.delete("/api/summary/conv_x")
    assert r.status_code == 200
    assert not (tmp_path / "conv_x.md").exists()


async def test_api_conv_summary_get_404(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    r = await api_client.get("/api/summary/conversation/nope/conv-missing")
    assert r.status_code == 200
    assert r.json()["status"] == "none"


async def test_api_conv_summary_request_404(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    r = await api_client.post("/api/summary/conversation/nope/conv-missing")
    assert r.status_code == 404


async def test_api_conv_summary_request_starts_segments(seed_sessions, api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    # s1 has conv-1 with 2 segments under project conversations
    r = await api_client.post("/api/summary/conversation/conversations/conv-1")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    # Segment inputs enqueued
    assert (tmp_path / "seg-1a.input").exists()
    assert (tmp_path / "seg-1b.input").exists()


async def test_api_conv_summary_get_with_seeded_segments(seed_sessions, api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    r = await api_client.get("/api/summary/conversation/conversations/conv-1")
    assert r.status_code == 200
    # Should trigger segments phase and return pending
    assert r.json()["status"] == "pending"


async def test_api_conv_summary_ready_path(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr(summaries_mod, "SUMMARIES_DIR", tmp_path)
    key = "conv_proj_conv-id"
    (tmp_path / f"{key}.md").write_text("TITLE: Done\n\nx", encoding="utf-8")
    (tmp_path / f"{key}.pending").write_text("", encoding="utf-8")
    # Even without matching DB rows, ready md short-circuits
    r = await api_client.get("/api/summary/conversation/proj/conv-id")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
