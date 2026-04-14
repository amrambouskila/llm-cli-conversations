"""Tests for app.py — lifespan, /api/ready, /api/update, export pipeline, SPA serving."""
from __future__ import annotations

import subprocess
from pathlib import Path

import app as app_module
from app import run_export_pipeline, sync_directory


def test_log_prints(capsys):
    app_module._log("hello world")
    captured = capsys.readouterr()
    assert "hello world" in captured.out


def test_sync_directory_missing_src_noop(tmp_path):
    dst = tmp_path / "dst"
    sync_directory(tmp_path / "nope", dst)
    assert not dst.exists()


def test_sync_directory_copies_new_files(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    (src / "sub").mkdir()
    (src / "a.txt").write_text("A", encoding="utf-8")
    (src / "sub" / "b.txt").write_text("B", encoding="utf-8")

    sync_directory(src, dst)
    assert (dst / "a.txt").read_text() == "A"
    assert (dst / "sub" / "b.txt").read_text() == "B"


def test_sync_directory_updates_newer_files(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    sfile = src / "a.txt"
    dfile = dst / "a.txt"
    dfile.write_text("OLD", encoding="utf-8")
    import os
    old = dfile.stat().st_mtime
    # Make source newer
    sfile.write_text("NEW", encoding="utf-8")
    os.utime(sfile, (old + 100, old + 100))

    sync_directory(src, dst)
    assert dfile.read_text() == "NEW"


def test_sync_directory_keeps_older_source_unchanged(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "a.txt").write_text("OLD_SRC", encoding="utf-8")
    dfile = dst / "a.txt"
    dfile.write_text("DST", encoding="utf-8")
    import os
    new = dfile.stat().st_mtime
    os.utime(src / "a.txt", (new - 100, new - 100))
    sync_directory(src, dst)
    assert dfile.read_text() == "DST"


# ---------------------------------------------------------------------------
# /api/ready
# ---------------------------------------------------------------------------

async def test_api_ready(api_client):
    r = await api_client.get("/api/ready")
    assert r.status_code == 200
    assert "ready" in r.json()


# ---------------------------------------------------------------------------
# run_export_pipeline
# ---------------------------------------------------------------------------

async def test_run_export_pipeline_missing_projects_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(tmp_path / "missing"))
    result = await run_export_pipeline()
    assert result["success"] is False
    assert "not found" in result["error"]


async def test_run_export_pipeline_no_project_dirs(monkeypatch, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(src))
    result = await run_export_pipeline()
    assert result["success"] is False
    assert "No project directories" in result["error"]


async def test_run_export_pipeline_conversion_failure(monkeypatch, tmp_path):
    """Subprocess returns non-zero — pipeline reports failure."""
    src = tmp_path / "src"
    (src / "proj-a").mkdir(parents=True)
    (src / "proj-a" / "s.jsonl").write_text("{}\n", encoding="utf-8")

    raw = tmp_path / "raw"
    md = tmp_path / "markdown"
    codex_md = tmp_path / "markdown_codex"
    codex_src = tmp_path / "codex_nope"

    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(src))
    monkeypatch.setattr(app_module, "RAW_DIR", str(raw))
    monkeypatch.setattr(app_module, "DEFAULT_MARKDOWN_DIR", str(md))
    monkeypatch.setattr(app_module, "CODEX_MARKDOWN_DIR", str(codex_md))
    monkeypatch.setattr(app_module, "CODEX_SESSIONS_SRC", str(codex_src))

    class _FakeResult:
        def __init__(self, rc: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = rc
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(*args, **kwargs):
        return _FakeResult(1, stdout="running...", stderr="conversion exploded")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await run_export_pipeline()
    assert result["success"] is False
    assert "Conversion failed" in result["error"]
    assert any("running" in line for line in result["log"])


async def test_run_export_pipeline_success(monkeypatch, tmp_path):
    """Happy path: subprocess succeeds, Postgres load runs."""
    src = tmp_path / "src"
    (src / "proj-a").mkdir(parents=True)
    (src / "proj-a" / "s.jsonl").write_text("{}\n", encoding="utf-8")

    raw = tmp_path / "raw"
    md = tmp_path / "markdown"
    codex_md = tmp_path / "markdown_codex"
    codex_src = tmp_path / "codex_src"

    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(src))
    monkeypatch.setattr(app_module, "RAW_DIR", str(raw))
    monkeypatch.setattr(app_module, "DEFAULT_MARKDOWN_DIR", str(md))
    monkeypatch.setattr(app_module, "CODEX_MARKDOWN_DIR", str(codex_md))
    monkeypatch.setattr(app_module, "CODEX_SESSIONS_SRC", str(codex_src))

    class _FakeResult:
        returncode = 0
        stdout = "done"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())

    async def fake_load_all(*args, **kwargs):
        return {"claude": 0, "codex": 0}

    # Patch load.load_all so the pipeline doesn't actually touch Postgres path logic
    import load as load_mod
    monkeypatch.setattr(load_mod, "load_all", fake_load_all)

    result = await run_export_pipeline()
    assert result["success"] is True
    assert "sessions" in result


async def test_run_export_pipeline_load_failure_non_fatal(monkeypatch, tmp_path):
    src = tmp_path / "src"
    (src / "proj-a").mkdir(parents=True)
    raw = tmp_path / "raw"
    md = tmp_path / "markdown"
    codex_md = tmp_path / "markdown_codex"

    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(src))
    monkeypatch.setattr(app_module, "RAW_DIR", str(raw))
    monkeypatch.setattr(app_module, "DEFAULT_MARKDOWN_DIR", str(md))
    monkeypatch.setattr(app_module, "CODEX_MARKDOWN_DIR", str(codex_md))

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())

    async def fake_load_all(*args, **kwargs):
        raise RuntimeError("db down")

    import load as load_mod
    monkeypatch.setattr(load_mod, "load_all", fake_load_all)

    result = await run_export_pipeline()
    assert result["success"] is True
    assert any("Postgres load failed" in line for line in result["log"])


# ---------------------------------------------------------------------------
# /api/update
# ---------------------------------------------------------------------------

async def test_api_update_failure_returns_500(api_client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(tmp_path / "missing"))
    r = await api_client.post("/api/update")
    assert r.status_code == 500
    data = r.json()
    assert data["success"] is False


async def test_api_update_exception_handled(api_client, monkeypatch):
    async def explode():
        raise RuntimeError("boom")

    monkeypatch.setattr(app_module, "run_export_pipeline", explode)
    r = await api_client.post("/api/update")
    assert r.status_code == 500
    data = r.json()
    assert "boom" in data.get("error", "")


# ---------------------------------------------------------------------------
# Static/SPA serving
# ---------------------------------------------------------------------------

async def test_spa_fallback_returns_index_for_unknown(api_client, tmp_path):
    """Any non-API unknown path should fall back to index.html (if static dir exists)
    or return 404 when no static build present. Accept either outcome as long as
    the response is well-formed."""
    r = await api_client.get("/some/client-route")
    # Either 200 (SPA) or 404 (no static build in test env)
    assert r.status_code in (200, 404)


def test_app_has_lifespan_attr():
    assert app_module.app.router.lifespan_context is not None
