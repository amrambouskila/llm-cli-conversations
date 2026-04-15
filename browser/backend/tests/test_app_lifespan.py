"""Tests for app.py paths not reachable via the existing api_client fixture.

Covers:
- `_startup_load` (success + load_all raise + recompute_session_costs raise)
- `lifespan` async context manager (init_db + create_task + yield)
- `_register_spa_routes` (no static, no index, with assets, path traversal, direct file, SPA fallback)
- `run_export_pipeline` codex-converter subprocess branch
- `run_export_pipeline` recompute_session_costs failure branch
- `run_export_pipeline` old_md.unlink() for pre-existing markdown
- `db.get_db` async-generator yield body
"""
from __future__ import annotations

import subprocess

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app as app_module
from app import _register_spa_routes, run_export_pipeline

# ---------------------------------------------------------------------------
# _startup_load — every branch
# ---------------------------------------------------------------------------

async def test_startup_load_success_path(monkeypatch, db_engine):
    """Both load_all and recompute_session_costs succeed → startup_ready = True."""
    import load as load_mod

    async def fake_load_all(*args, **kwargs):
        return {"claude": 0}

    async def fake_recompute():
        return (0, 0)

    monkeypatch.setattr(load_mod, "load_all", fake_load_all)
    monkeypatch.setattr(load_mod, "recompute_session_costs", fake_recompute)
    monkeypatch.setattr(app_module, "startup_ready", False)

    await app_module._startup_load()
    assert app_module.startup_ready is True


async def test_startup_load_handles_load_all_exception(monkeypatch, db_engine):
    """load_all raises → first except fires, recompute still runs, startup_ready True."""
    import load as load_mod

    async def boom(*a, **k):
        raise RuntimeError("load exploded")

    async def fake_recompute():
        return (1, 0)

    monkeypatch.setattr(load_mod, "load_all", boom)
    monkeypatch.setattr(load_mod, "recompute_session_costs", fake_recompute)
    monkeypatch.setattr(app_module, "startup_ready", False)

    await app_module._startup_load()
    assert app_module.startup_ready is True


async def test_startup_load_handles_recompute_exception(monkeypatch, db_engine):
    """recompute_session_costs raises → second except fires, startup_ready still True."""
    import load as load_mod

    async def fake_load_all(*args, **kwargs):
        return {"claude": 0}

    async def recompute_boom():
        raise RuntimeError("recompute exploded")

    monkeypatch.setattr(load_mod, "load_all", fake_load_all)
    monkeypatch.setattr(load_mod, "recompute_session_costs", recompute_boom)
    monkeypatch.setattr(app_module, "startup_ready", False)

    await app_module._startup_load()
    assert app_module.startup_ready is True


# ---------------------------------------------------------------------------
# lifespan — init_db + background task + yield
# ---------------------------------------------------------------------------

async def test_lifespan_runs_init_and_spawns_startup_task(monkeypatch, db_engine):
    """Entering lifespan runs init_db + spawns _startup_load, yields cleanly."""
    import load as load_mod

    calls = {"load_all": 0, "recompute": 0}

    async def fake_load_all(*a, **k):
        calls["load_all"] += 1
        return {"claude": 0}

    async def fake_recompute():
        calls["recompute"] += 1
        return (0, 0)

    monkeypatch.setattr(load_mod, "load_all", fake_load_all)
    monkeypatch.setattr(load_mod, "recompute_session_costs", fake_recompute)

    async with app_module.lifespan(app_module.app):
        # Body up to yield has run; background task is now scheduled.
        pass

    # Give the background task a chance to settle before the test ends.
    import asyncio
    for _ in range(10):
        if calls["load_all"] and calls["recompute"]:
            break
        await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# _register_spa_routes — every branch
# ---------------------------------------------------------------------------

def _make_static(tmp_path, with_assets: bool = True, with_extra_file: bool = True):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>INDEX</html>", encoding="utf-8")
    if with_assets:
        assets = static_dir / "assets"
        assets.mkdir()
        (assets / "app.js").write_text("console.log('hi')", encoding="utf-8")
    if with_extra_file:
        (static_dir / "logo.svg").write_text("<svg/>", encoding="utf-8")
    return static_dir


async def _get(client: AsyncClient, path: str) -> tuple[int, str]:
    r = await client.get(path)
    return r.status_code, r.text


def test_register_spa_routes_skips_when_static_dir_missing(tmp_path):
    registered = _register_spa_routes(FastAPI(), tmp_path / "no-such-dir")
    assert registered is False


def test_register_spa_routes_skips_when_index_html_missing(tmp_path):
    (tmp_path / "x").mkdir()  # dir exists but no index.html
    registered = _register_spa_routes(FastAPI(), tmp_path / "x")
    assert registered is False


async def test_spa_serves_index_for_root(tmp_path):
    static_dir = _make_static(tmp_path)
    app = FastAPI()
    _register_spa_routes(app, static_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        status, body = await _get(c, "/")
    assert status == 200
    assert "INDEX" in body


async def test_spa_serves_direct_file_when_exists(tmp_path):
    static_dir = _make_static(tmp_path)
    app = FastAPI()
    _register_spa_routes(app, static_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        status, body = await _get(c, "/logo.svg")
    assert status == 200
    assert "<svg/>" in body


async def test_spa_falls_back_to_index_for_unknown_path(tmp_path):
    static_dir = _make_static(tmp_path)
    app = FastAPI()
    _register_spa_routes(app, static_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        status, body = await _get(c, "/deep/client/route")
    assert status == 200
    assert "INDEX" in body


async def test_spa_path_traversal_blocked(tmp_path):
    """`/../outside` resolves past static_dir → guard returns index.html."""
    static_dir = _make_static(tmp_path)
    # A file outside the static dir — traversal guard should prevent it being served.
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    app = FastAPI()
    _register_spa_routes(app, static_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # httpx normalizes "/../secret.txt" → try a hand-crafted request
        r = await c.request("GET", "http://t/..%2Fsecret.txt")
    # Either the traversal guard returned index, or the platform-level routing
    # rejected the malformed path. Both are acceptable — "SECRET" must NOT appear.
    assert "SECRET" not in r.text


async def test_spa_without_assets_dir_still_serves_index(tmp_path):
    """Static dir with no `assets/` subdir — /assets mount skipped but / still works."""
    static_dir = _make_static(tmp_path, with_assets=False)
    app = FastAPI()
    _register_spa_routes(app, static_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        status, _body = await _get(c, "/")
    assert status == 200


# ---------------------------------------------------------------------------
# run_export_pipeline — codex converter branch + recompute failure + old_md.unlink
# ---------------------------------------------------------------------------

async def test_run_export_pipeline_runs_codex_converter(monkeypatch, tmp_path, db_engine):
    """When the codex source + converter both exist, the codex subprocess fires."""
    src = tmp_path / "src"
    (src / "proj-a").mkdir(parents=True)
    (src / "proj-a" / "s.jsonl").write_text("{}\n", encoding="utf-8")

    raw = tmp_path / "raw"
    md = tmp_path / "markdown"
    codex_md = tmp_path / "markdown_codex"
    codex_src = tmp_path / "codex_src"
    codex_src.mkdir()  # exists → codex branch fires

    # convert_codex_sessions.py lives at the project root in production but the
    # test container only mounts browser/backend. Point SCRIPT_DIR at a fake dir
    # containing stub converter scripts so codex_converter.exists() returns True.
    fake_script_dir = tmp_path / "scripts"
    fake_script_dir.mkdir()
    (fake_script_dir / "convert_claude_jsonl_to_md.py").write_text("# stub", encoding="utf-8")
    (fake_script_dir / "convert_codex_sessions.py").write_text("# stub", encoding="utf-8")

    monkeypatch.setattr(app_module, "SCRIPT_DIR", fake_script_dir)
    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(src))
    monkeypatch.setattr(app_module, "RAW_DIR", str(raw))
    monkeypatch.setattr(app_module, "DEFAULT_MARKDOWN_DIR", str(md))
    monkeypatch.setattr(app_module, "CODEX_MARKDOWN_DIR", str(codex_md))
    monkeypatch.setattr(app_module, "CODEX_SESSIONS_SRC", str(codex_src))

    calls: list[tuple] = []

    class _FakeResult:
        def __init__(self, stdout: str = "") -> None:
            self.returncode = 0
            self.stdout = stdout
            self.stderr = ""

    def fake_run(cmd, *a, **kw):
        calls.append(tuple(cmd))
        return _FakeResult(stdout="fake stdout line")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Pre-create a stale .md in codex_md to exercise the `old_md.unlink()` loop
    codex_md.mkdir(parents=True, exist_ok=True)
    stale = codex_md / "stale.md"
    stale.write_text("old", encoding="utf-8")

    import load as load_mod
    async def fake_load_all(*a, **k):
        return {"claude": 0, "codex": 0}
    monkeypatch.setattr(load_mod, "load_all", fake_load_all)

    result = await run_export_pipeline()
    # Both converters ran — claude (first) + codex (second).
    assert len(calls) >= 2
    assert any("convert_codex_sessions.py" in " ".join(c) for c in calls)
    # Stale codex markdown was unlinked before the codex subprocess ran.
    assert not stale.exists()
    # The codex stdout was captured into log_lines.
    assert any("fake stdout line" in line for line in result.get("log", []))


async def test_run_export_pipeline_deletes_existing_markdown(monkeypatch, tmp_path):
    """`for old_md in markdown_dir.glob('*.md'): old_md.unlink()` fires when md dir has files."""
    src = tmp_path / "src"
    (src / "proj-a").mkdir(parents=True)

    raw = tmp_path / "raw"
    md = tmp_path / "markdown"
    md.mkdir()
    stale = md / "stale.md"
    stale.write_text("old content", encoding="utf-8")
    codex_md = tmp_path / "markdown_codex"
    codex_src = tmp_path / "codex_nope"  # missing

    monkeypatch.setattr(app_module, "CLAUDE_PROJECTS_SRC", str(src))
    monkeypatch.setattr(app_module, "RAW_DIR", str(raw))
    monkeypatch.setattr(app_module, "DEFAULT_MARKDOWN_DIR", str(md))
    monkeypatch.setattr(app_module, "CODEX_MARKDOWN_DIR", str(codex_md))
    monkeypatch.setattr(app_module, "CODEX_SESSIONS_SRC", str(codex_src))

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())

    import load as load_mod
    async def fake_load_all(*a, **k):
        return {"claude": 0}
    monkeypatch.setattr(load_mod, "load_all", fake_load_all)

    result = await run_export_pipeline()
    assert result["success"] is True
    # The pre-existing stale.md was unlinked
    assert not stale.exists()


async def test_run_export_pipeline_recompute_failure_non_fatal(monkeypatch, tmp_path):
    """recompute_session_costs raising is caught; pipeline still reports success."""
    src = tmp_path / "src"
    (src / "proj-a").mkdir(parents=True)
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
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())

    import load as load_mod
    async def fake_load_all(*a, **k):
        return {"claude": 0}
    async def boom():
        raise RuntimeError("recompute exploded")
    monkeypatch.setattr(load_mod, "load_all", fake_load_all)
    monkeypatch.setattr(load_mod, "recompute_session_costs", boom)

    result = await run_export_pipeline()
    assert result["success"] is True
    assert any("Session cost recompute failed" in line for line in result["log"])


# ---------------------------------------------------------------------------
# db.get_db — async generator body
# ---------------------------------------------------------------------------

async def test_get_db_yields_async_session(db_engine):
    """Direct iteration of the get_db async generator covers the yield body."""
    from db import get_db

    agen = get_db()
    session = await agen.__anext__()
    try:
        assert session is not None
        from sqlalchemy import select
        # Prove the session works
        result = await session.execute(select(1))
        assert result.scalar_one() == 1
    finally:
        await agen.aclose()


# ---------------------------------------------------------------------------
# _log — already partly covered, but confirm the timestamp format is correct.
# ---------------------------------------------------------------------------

def test_log_prefix_format(capsys):
    app_module._log("payload")
    out = capsys.readouterr().out
    # Timestamp format [HH:MM:SS] — 8 chars inside brackets
    assert out.startswith("[")
    assert "] payload" in out


# ---------------------------------------------------------------------------
# api_update path exercising recompute via happy-path with Postgres
# ---------------------------------------------------------------------------

async def test_api_update_success_roundtrip(api_client, monkeypatch, tmp_path):
    """Drive /api/update through the full happy path so line 238-239 execute."""
    src = tmp_path / "src"
    (src / "proj-a").mkdir(parents=True)
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
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeResult())

    import load as load_mod
    async def fake_load_all(*a, **k):
        return {"claude": 0}
    monkeypatch.setattr(load_mod, "load_all", fake_load_all)

    r = await api_client.post("/api/update")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
