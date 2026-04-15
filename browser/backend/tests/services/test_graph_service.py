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


# ---------------------------------------------------------------------------
# Wiki surface (Phase 8)
# ---------------------------------------------------------------------------

class TestWikiSlugParity:
    """Lock `GraphService._wiki_slug` to graphify.wiki._safe_filename exactly."""

    @pytest.mark.parametrize(
        "label",
        [
            "Community 1",
            "docker",
            "React + TypeScript",
            "path/with/slashes",
            "colon:separated",
            "multi word label with spaces",
            "trailing space ",
            " leading space",
            "a/b:c d",
            "numbers-123",
            "CamelCase",
            "snake_case",
            "mixed/slash:colon space",
            "",
            "x",
            "unicode-\u00e9\u00e8",
        ],
    )
    def test_matches_graphify_safe_filename(self, label):
        from graphify.wiki import _safe_filename

        assert GraphService._wiki_slug(label) == _safe_filename(label)


# -- _safe_wiki_path ----------------------------------------------------------

def test_safe_wiki_path_returns_none_when_wiki_dir_missing(db_session, tmp_path):
    svc = GraphService(db_session)
    # tmp_path exists but wiki/ does not
    assert svc._safe_wiki_path("anything") is None


def test_safe_wiki_path_returns_file_when_valid(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "docker.md").write_text("# docker\n", encoding="utf-8")
    svc = GraphService(db_session)
    target = svc._safe_wiki_path("docker")
    assert target is not None
    assert target.name == "docker.md"


def test_safe_wiki_path_rejects_traversal_with_parent(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "OUTSIDE.md").write_text("outside", encoding="utf-8")
    svc = GraphService(db_session)
    assert svc._safe_wiki_path("../OUTSIDE") is None


def test_safe_wiki_path_returns_none_when_target_is_not_a_file(db_session, tmp_path):
    """Slug pointing at a directory (e.g. a subdirectory named foo.md) is rejected."""
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "subdir.md").mkdir()  # bizarre but allowed on disk
    svc = GraphService(db_session)
    assert svc._safe_wiki_path("subdir") is None


def test_safe_wiki_path_missing_file_returns_none(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    svc = GraphService(db_session)
    assert svc._safe_wiki_path("does_not_exist") is None


# -- _extract_title -----------------------------------------------------------

def test_extract_title_uses_first_h1():
    assert GraphService._extract_title("# Hello\n\nbody", "fb") == "Hello"


def test_extract_title_falls_back_when_h1_empty():
    assert GraphService._extract_title("# \nbody", "fb") == "fb"


def test_extract_title_falls_back_when_no_h1():
    assert GraphService._extract_title("body only", "fb") == "fb"


# -- _parse_index_articles ----------------------------------------------------

def test_parse_index_articles_extracts_community_and_god_nodes(db_session):
    svc = GraphService(db_session)
    md = (
        "# Knowledge Graph Index\n\n"
        "## Communities\n"
        "- [[Alpha]] \u2014 5 nodes\n"
        "- [[Beta/Rev]] \u2014 3 nodes\n"
        "## God Nodes\n"
        "- [[docker]] \u2014 10 connections\n"
    )
    articles = svc._parse_index_articles(md)
    assert articles == [
        {"slug": "Alpha", "title": "Alpha", "kind": "community"},
        {"slug": "Beta-Rev", "title": "Beta/Rev", "kind": "community"},
        {"slug": "docker", "title": "docker", "kind": "god_node"},
    ]


def test_parse_index_articles_skips_other_sections(db_session):
    svc = GraphService(db_session)
    md = (
        "## Overview\n"
        "- [[ignored link]] somewhere\n"
        "## Communities\n"
        "- [[Kept]]\n"
    )
    articles = svc._parse_index_articles(md)
    assert articles == [{"slug": "Kept", "title": "Kept", "kind": "community"}]


def test_parse_index_articles_skips_empty_and_index_labels(db_session):
    svc = GraphService(db_session)
    md = (
        "## Communities\n"
        "- [[   ]] blank label\n"
        "- [[index]] self reference\n"
        "- [[Valid]] kept\n"
    )
    articles = svc._parse_index_articles(md)
    assert articles == [{"slug": "Valid", "title": "Valid", "kind": "community"}]


def test_parse_index_articles_deduplicates_by_slug(db_session):
    svc = GraphService(db_session)
    md = (
        "## Communities\n"
        "- [[Same]] one\n"
        "- [[Same]] two\n"
    )
    articles = svc._parse_index_articles(md)
    assert articles == [{"slug": "Same", "title": "Same", "kind": "community"}]


def test_parse_index_articles_resets_kind_on_non_target_heading(db_session):
    svc = GraphService(db_session)
    md = (
        "## Communities\n"
        "- [[InCommunities]]\n"
        "## Summary\n"
        "- [[IgnoredUnderSummary]]\n"
    )
    articles = svc._parse_index_articles(md)
    assert articles == [
        {"slug": "InCommunities", "title": "InCommunities", "kind": "community"}
    ]


# -- load_wiki_index / load_wiki_article / resolve_wiki_slug -----------------

async def test_load_wiki_index_none_when_missing(db_session, tmp_path):
    # tmp_path has no wiki/ at all
    data = await GraphService(db_session).load_wiki_index()
    assert data is None


async def test_load_wiki_index_none_when_index_md_missing(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    data = await GraphService(db_session).load_wiki_index()
    assert data is None


async def test_load_wiki_index_returns_dict(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "index.md").write_text(
        "# Custom Title\n\n## Communities\n- [[A]]\n",
        encoding="utf-8",
    )
    data = await GraphService(db_session).load_wiki_index()
    assert data["title"] == "Custom Title"
    assert data["articles"] == [{"slug": "A", "title": "A", "kind": "community"}]


async def test_load_wiki_article_none_when_missing(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    data = await GraphService(db_session).load_wiki_article("nope")
    assert data is None


async def test_load_wiki_article_returns_dict(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "docker.md").write_text(
        "# Docker\n\nContent.\n", encoding="utf-8"
    )
    data = await GraphService(db_session).load_wiki_article("docker")
    assert data == {"slug": "docker", "title": "Docker", "markdown": "# Docker\n\nContent.\n"}


async def test_resolve_wiki_slug_god_node_first(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "docker.md").write_text("# docker\n", encoding="utf-8")
    (tmp_path / "wiki" / "Community_2.md").write_text("# Community 2\n", encoding="utf-8")
    db_session.add(Concept(id="c1", name="docker", community_id=2, degree=5))
    await db_session.commit()

    slug = await GraphService(db_session).resolve_wiki_slug(
        concept_id="c1", concept_name="docker"
    )
    assert slug == "docker"


async def test_resolve_wiki_slug_falls_back_to_community(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "Community_3.md").write_text("# Community 3\n", encoding="utf-8")
    db_session.add(Concept(id="c2", name="novel", community_id=3, degree=1))
    await db_session.commit()

    slug = await GraphService(db_session).resolve_wiki_slug(
        concept_id="c2", concept_name="novel"
    )
    assert slug == "Community_3"


async def test_resolve_wiki_slug_returns_none_when_nothing_matches(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    slug = await GraphService(db_session).resolve_wiki_slug(
        concept_id=None, concept_name=None
    )
    assert slug is None


async def test_resolve_wiki_slug_concept_id_without_community(db_session, tmp_path):
    (tmp_path / "wiki").mkdir()
    db_session.add(Concept(id="c3", name="orphan", community_id=None, degree=0))
    await db_session.commit()

    slug = await GraphService(db_session).resolve_wiki_slug(
        concept_id="c3", concept_name=None
    )
    assert slug is None


async def test_resolve_wiki_slug_concept_id_with_community_but_article_missing(
    db_session, tmp_path
):
    (tmp_path / "wiki").mkdir()
    # Community 77 exists in DB but no article file
    db_session.add(Concept(id="c4", name="x", community_id=77, degree=0))
    await db_session.commit()

    slug = await GraphService(db_session).resolve_wiki_slug(
        concept_id="c4", concept_name=None
    )
    assert slug is None
