"""Unit tests for GraphService — file-pipeline status, trigger, import."""
from __future__ import annotations

import json

import pytest

from models import Concept
from services.graph_service import GraphService


@pytest.fixture(autouse=True)
def _point_graphify_out_to_tmp(tmp_path, monkeypatch):
    """Redirect GRAPHIFY_OUT so tests don't touch /data/graphify-out."""
    monkeypatch.setattr("services.dashboard_service.GRAPHIFY_OUT", tmp_path)
    return tmp_path


async def test_status_none_when_no_files(db_session):
    data = await GraphService(db_session).get_status()
    assert data["status"] == "none"
    assert data["has_data"] is False
    assert data["progress"] is None


async def test_status_ready_when_graph_json_exists(db_session, tmp_path):
    (tmp_path / "graph.json").write_text("{}", encoding="utf-8")
    data = await GraphService(db_session).get_status()
    assert data["status"] == "ready"


async def test_status_reads_explicit_status_file(db_session, tmp_path):
    (tmp_path / ".status").write_text("finished\n", encoding="utf-8")
    data = await GraphService(db_session).get_status()
    assert data["status"] == "finished"


async def test_status_generating_with_progress(db_session, tmp_path):
    (tmp_path / ".generate_requested").write_text("1", encoding="utf-8")
    (tmp_path / ".progress").write_text(json.dumps({
        "done": 5, "total": 10, "current": "a.md", "ok": 4, "failed": 1, "model": "opus",
    }), encoding="utf-8")
    data = await GraphService(db_session).get_status()
    assert data["status"] == "generating"
    assert data["progress"]["done"] == 5


async def test_status_generating_without_progress_defaults(db_session, tmp_path):
    (tmp_path / ".generate_requested").write_text("1", encoding="utf-8")
    data = await GraphService(db_session).get_status()
    assert data["status"] == "generating"
    assert data["progress"] == {
        "done": 0, "total": 0, "current": None, "ok": 0, "failed": 0, "model": "",
    }


async def test_status_has_data_flag_follows_concept_count(db_session, tmp_path):
    db_session.add(Concept(id="c1", name="docker", community_id=1, degree=1))
    await db_session.commit()
    data = await GraphService(db_session).get_status()
    assert data["has_data"] is True


async def test_trigger_regeneration_writes_files(db_session, tmp_path):
    data = await GraphService(db_session).trigger_regeneration()
    assert data == {"status": "generating"}
    assert (tmp_path / ".generate_requested").exists()
    assert (tmp_path / ".status").read_text() == "generating"


async def test_import_from_disk_no_file(db_session):
    data = await GraphService(db_session).import_from_disk()
    assert data == {"ok": False, "error": "No graph.json found"}


async def test_import_from_disk_with_minimal_file(db_session, tmp_path):
    minimal = {
        "nodes": [{"id": "n1", "label": "docker", "source_file": "/anywhere/x.md"}],
        "links": [],
    }
    (tmp_path / "graph.json").write_text(json.dumps(minimal), encoding="utf-8")
    data = await GraphService(db_session).import_from_disk()
    assert data == {"ok": True}


async def test_status_progress_invalid_json_falls_back_to_defaults(db_session, tmp_path):
    """Corrupt .progress file → json.JSONDecodeError caught, progress defaults used."""
    (tmp_path / ".generate_requested").write_text("1", encoding="utf-8")
    (tmp_path / ".progress").write_text("{not valid json", encoding="utf-8")
    data = await GraphService(db_session).get_status()
    assert data["status"] == "generating"
    assert data["progress"] == {
        "done": 0, "total": 0, "current": None, "ok": 0, "failed": 0, "model": "",
    }


async def test_import_from_disk_raises_returns_error(db_session, tmp_path, monkeypatch):
    """Any exception from import_graph() is caught and surfaced as {ok: False, error: ...}."""
    (tmp_path / "graph.json").write_text(json.dumps({"nodes": [], "links": []}), encoding="utf-8")

    async def boom(path):
        raise RuntimeError("database exploded")

    import import_graph as ig
    monkeypatch.setattr(ig, "import_graph", boom)

    data = await GraphService(db_session).import_from_disk()
    assert data["ok"] is False
    assert "database exploded" in data["error"]
