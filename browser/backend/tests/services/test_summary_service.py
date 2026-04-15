"""Unit tests for SummaryService's service-layer API.

The filesystem state machine (_advance_conv_summary, _start_rollup_level, etc.)
is exhaustively tested in test_api_summaries.py via the module-level helpers.
This file pins down the class API surface: get/request/delete + get_all_titles.
"""
from __future__ import annotations

import pytest

from services import summary_service as sm
from services.summary_service import SummaryService


@pytest.fixture(autouse=True)
def _point_summary_dir_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SUMMARIES_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Segment summaries
# ---------------------------------------------------------------------------

def test_get_segment_summary_none_when_missing(db_session, tmp_path):
    svc = SummaryService(db_session)
    result = svc.get_segment_summary("missing")
    assert result["status"] == "none"


def test_get_segment_summary_ready_when_md_exists(db_session, tmp_path):
    (tmp_path / "seg-1a.md").write_text("TITLE: Docker fix\n\nbody", encoding="utf-8")
    svc = SummaryService(db_session)
    result = svc.get_segment_summary("seg-1a")
    assert result["status"] == "ready"
    assert result["title"] == "Docker fix"


async def test_request_segment_summary_404(db_session):
    """Unknown segment id returns None (route converts to 404)."""
    svc = SummaryService(db_session)
    assert await svc.request_segment_summary("no-such-segment") is None


async def test_request_segment_summary_enqueues_for_seeded(seed_sessions, db_session, tmp_path):
    svc = SummaryService(db_session)
    result = await svc.request_segment_summary("seg-1a")
    assert result["status"] == "pending"
    assert (tmp_path / "seg-1a.pending").exists()
    assert (tmp_path / "seg-1a.input").exists()


def test_delete_segment_summary_removes_files(db_session, tmp_path):
    for ext in (".md", ".pending", ".input"):
        (tmp_path / f"seg-1a{ext}").write_text("x", encoding="utf-8")
    SummaryService(db_session).delete_summary("seg-1a")
    for ext in (".md", ".pending", ".input"):
        assert not (tmp_path / f"seg-1a{ext}").exists()


def test_delete_conv_summary_uses_artifacts_path(db_session, tmp_path):
    """Conv keys start with 'conv_' and are cleaned via the state-machine path."""
    conv_key = "conv_proj_conv1"
    (tmp_path / f"{conv_key}.md").write_text("body", encoding="utf-8")
    (tmp_path / f"{conv_key}.state.json").write_text("{}", encoding="utf-8")
    SummaryService(db_session).delete_summary(conv_key)
    assert not (tmp_path / f"{conv_key}.md").exists()
    assert not (tmp_path / f"{conv_key}.state.json").exists()


# ---------------------------------------------------------------------------
# Conversation summaries
# ---------------------------------------------------------------------------

async def test_get_conversation_summary_none_when_missing(db_session):
    result = await SummaryService(db_session).get_conversation_summary("ghost", "x")
    # No DB segments → key-level "none" status returned
    assert result["status"] == "none"


async def test_request_conversation_summary_unknown_returns_none(db_session):
    result = await SummaryService(db_session).request_conversation_summary("ghost", "x")
    assert result is None


async def test_request_conversation_summary_with_seed_starts_state(seed_sessions, db_session, tmp_path):
    result = await SummaryService(db_session).request_conversation_summary(
        "conversations", "conv-1", "claude",
    )
    assert result is not None
    assert result["status"] == "pending"
    # State file should now exist for the conversation key
    assert (tmp_path / "conv_conversations_conv-1.state.json").exists()


# ---------------------------------------------------------------------------
# Bulk title lookup
# ---------------------------------------------------------------------------

def test_get_all_titles_empty_when_dir_missing(tmp_path, monkeypatch):
    """Re-point to a non-existent dir to verify the guard."""
    monkeypatch.setattr(sm, "SUMMARIES_DIR", tmp_path / "does-not-exist")
    assert SummaryService.get_all_titles() == {}


def test_get_all_titles_reads_md_files(tmp_path):
    (tmp_path / "seg-1.md").write_text("TITLE: First\n\nbody", encoding="utf-8")
    (tmp_path / "seg-2.md").write_text("TITLE: Second\n\nbody", encoding="utf-8")
    (tmp_path / "seg-3.md").write_text("no title here\n\nbody", encoding="utf-8")
    titles = SummaryService.get_all_titles()
    assert titles == {"seg-1": "First", "seg-2": "Second"}


def test_get_all_titles_skips_rollup_chunks(tmp_path):
    """Rollup chunks have `__` in the stem — those should be filtered out."""
    (tmp_path / "seg-1.md").write_text("TITLE: Seg\n\nbody", encoding="utf-8")
    (tmp_path / "conv_proj_c__r0_0.md").write_text("TITLE: Chunk\n\nbody", encoding="utf-8")
    titles = SummaryService.get_all_titles()
    assert "seg-1" in titles
    assert "conv_proj_c__r0_0" not in titles


def test_get_all_titles_skips_unreadable_file(tmp_path):
    """UnicodeDecodeError on read → file silently skipped, others still returned."""
    (tmp_path / "good.md").write_text("TITLE: Good\n\nbody", encoding="utf-8")
    # Raw invalid UTF-8 bytes — will raise UnicodeDecodeError on read_text(encoding="utf-8")
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe\x00\x00invalid-utf8")
    titles = SummaryService.get_all_titles()
    assert titles == {"good": "Good"}


# ---------------------------------------------------------------------------
# _advance_conv_summary — re-request missing segment on resumed run
# ---------------------------------------------------------------------------

def test_advance_conv_summary_re_requests_missing_segment(tmp_path):
    """State exists + one segment has no md/pending → service re-requests via _request_summary.

    Simulates the recovery path after a crash wipes a .pending file: the conversation
    state survives, but a child segment is in limbo. The next call must notice the
    missing pending and re-enqueue the job.
    """
    import json

    from services.summary_service import _advance_conv_summary

    key = "conv_proj_c1"
    # Write a state whose segments list contains "sk1" — which has NO .md and NO .pending.
    state = {
        "phase": "segments",
        "segment_keys": ["sk1"],
        "rollup_level": -1,
        "current_chunk_keys": [],
        "all_chunk_keys": [],
    }
    (tmp_path / f"{key}.state.json").write_text(json.dumps(state), encoding="utf-8")
    # Existing tests cover the happy path; here we leave sk1 completely absent.

    result = _advance_conv_summary(
        key,
        [{"id": "sk1", "raw_markdown": "some user message to summarize"}],
    )

    # _request_summary fires → a .pending marker + .input file now exist for sk1.
    assert (tmp_path / "sk1.pending").exists()
    assert (tmp_path / "sk1.input").read_text(encoding="utf-8") == "some user message to summarize"
    # State still in "segments" phase because sk1 is still not ready.
    assert result["status"] == "pending"
