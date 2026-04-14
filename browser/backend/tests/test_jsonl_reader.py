"""Tests for jsonl_reader extraction of model + token usage from raw JSONL."""
from __future__ import annotations

import json

from jsonl_reader import (
    SessionMetadata,
    _read_claude_jsonl,
    _read_codex_jsonl,
    read_claude_metadata,
    read_codex_metadata,
)


def _write_jsonl(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def test_session_metadata_defaults():
    m = SessionMetadata(session_id="abc")
    assert m.session_id == "abc"
    assert m.model is None
    assert m.input_tokens == 0
    assert m.cache_creation_tokens == 0


def test_read_claude_jsonl_extracts_model_and_usage(tmp_path):
    f = tmp_path / "uuid-1.jsonl"
    _write_jsonl(f, [
        {"type": "user", "message": {"content": "hi"}},
        {"type": "assistant", "message": {
            "model": "claude-opus-4",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_input_tokens": 20,
                "cache_creation_input_tokens": 5,
            },
        }},
        {"type": "assistant", "message": {
            "model": "claude-opus-4",
            "usage": {"input_tokens": 200, "output_tokens": 75},
        }},
    ])
    meta = _read_claude_jsonl(f)
    assert meta is not None
    assert meta.session_id == "uuid-1"
    assert meta.model == "claude-opus-4"
    assert meta.input_tokens == 300
    assert meta.output_tokens == 125
    assert meta.cache_read_tokens == 20
    assert meta.cache_creation_tokens == 5


def test_read_claude_jsonl_handles_blank_and_malformed_lines(tmp_path):
    f = tmp_path / "u.jsonl"
    f.write_text(
        "\n"
        "not-json\n"
        + json.dumps({"type": "assistant", "message": {"model": "m", "usage": {"input_tokens": 1}}})
        + "\n",
        encoding="utf-8",
    )
    meta = _read_claude_jsonl(f)
    assert meta is not None
    assert meta.model == "m"
    assert meta.input_tokens == 1


def test_read_claude_jsonl_skips_subagent(tmp_path):
    sub = tmp_path / "subagents"
    sub.mkdir()
    f = sub / "u.jsonl"
    f.write_text("{}\n", encoding="utf-8")
    assert _read_claude_jsonl(f) is None


def test_read_claude_jsonl_missing_file_returns_none(tmp_path):
    meta = _read_claude_jsonl(tmp_path / "nope.jsonl")
    assert meta is None


def test_read_codex_jsonl_extracts_session_meta(tmp_path):
    f = tmp_path / "codex.jsonl"
    _write_jsonl(f, [
        {"type": "session_meta", "payload": {"id": "sid-42", "model_provider": "openai"}},
        {"type": "other"},
    ])
    meta = _read_codex_jsonl(f)
    assert meta is not None
    assert meta.session_id == "sid-42"
    assert meta.model_provider == "openai"


def test_read_codex_jsonl_no_session_meta_returns_none(tmp_path):
    f = tmp_path / "codex.jsonl"
    _write_jsonl(f, [{"type": "other"}])
    assert _read_codex_jsonl(f) is None


def test_read_codex_jsonl_handles_bad_lines(tmp_path):
    f = tmp_path / "codex.jsonl"
    f.write_text(
        "\n"
        "not-json\n"
        + json.dumps({"type": "session_meta", "payload": {"model_provider": "openai"}})
        + "\n",
        encoding="utf-8",
    )
    meta = _read_codex_jsonl(f)
    # No explicit id -> uses stem
    assert meta is not None
    assert meta.session_id == "codex"


def test_read_codex_jsonl_missing_file(tmp_path):
    assert _read_codex_jsonl(tmp_path / "missing.jsonl") is None


def test_read_claude_metadata_missing_dir(tmp_path):
    assert read_claude_metadata(str(tmp_path / "nope")) == {}


def test_read_claude_metadata_scans_projects(tmp_path):
    proj = tmp_path / "proj-a"
    proj.mkdir()
    f = proj / "session-1.jsonl"
    _write_jsonl(f, [{"type": "assistant", "message": {"model": "opus", "usage": {"input_tokens": 10}}}])
    # non-dir at top level is skipped
    (tmp_path / "stray.txt").write_text("x", encoding="utf-8")
    results = read_claude_metadata(str(tmp_path))
    assert "session-1" in results
    assert results["session-1"].model == "opus"


def test_read_codex_metadata_missing_dir(tmp_path):
    assert read_codex_metadata(str(tmp_path / "nope")) == {}


def test_read_codex_metadata_scans(tmp_path):
    nested = tmp_path / "2026" / "03"
    nested.mkdir(parents=True)
    f = nested / "codex.jsonl"
    _write_jsonl(f, [{"type": "session_meta", "payload": {"id": "abc", "model_provider": "openai"}}])
    results = read_codex_metadata(str(tmp_path))
    assert "abc" in results
    assert results["abc"].model_provider == "openai"
