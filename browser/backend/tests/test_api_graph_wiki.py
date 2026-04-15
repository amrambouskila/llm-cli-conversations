"""Integration tests for /api/graph/wiki/* — Phase 8."""
from __future__ import annotations

import pytest


@pytest.fixture
def wiki_dir(tmp_path, monkeypatch):
    """Redirect GRAPHIFY_OUT to tmp_path and create wiki/ under it."""
    monkeypatch.setattr("services.dashboard_service.GRAPHIFY_OUT", tmp_path)
    wdir = tmp_path / "wiki"
    wdir.mkdir()
    return wdir


# ---------------------------------------------------------------------------
# /api/graph/wiki/index
# ---------------------------------------------------------------------------

async def test_index_404_when_wiki_dir_missing(api_client, tmp_path, monkeypatch):
    monkeypatch.setattr("services.dashboard_service.GRAPHIFY_OUT", tmp_path)
    r = await api_client.get("/api/graph/wiki/index")
    assert r.status_code == 404


async def test_index_404_when_index_file_missing(api_client, wiki_dir):
    # wiki/ exists but index.md doesn't
    r = await api_client.get("/api/graph/wiki/index")
    assert r.status_code == 404


async def test_index_happy_path(api_client, wiki_dir):
    (wiki_dir / "index.md").write_text(
        "# Knowledge Graph Index\n"
        "\n"
        "> intro line\n"
        "\n"
        "## Communities\n"
        "- [[Community 1]] \u2014 5 nodes\n"
        "- [[Community 2]] \u2014 3 nodes\n"
        "\n"
        "## God Nodes\n"
        "- [[docker]] \u2014 10 connections\n",
        encoding="utf-8",
    )
    (wiki_dir / "Community_1.md").write_text("# Community 1\n", encoding="utf-8")
    (wiki_dir / "Community_2.md").write_text("# Community 2\n", encoding="utf-8")
    (wiki_dir / "docker.md").write_text("# docker\n", encoding="utf-8")

    r = await api_client.get("/api/graph/wiki/index")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "Knowledge Graph Index"
    assert "## Communities" in data["markdown"]

    slugs = {a["slug"]: a["kind"] for a in data["articles"]}
    assert slugs == {
        "Community_1": "community",
        "Community_2": "community",
        "docker": "god_node",
    }


# ---------------------------------------------------------------------------
# /api/graph/wiki/{slug}
# ---------------------------------------------------------------------------

async def test_article_happy_path(api_client, wiki_dir):
    (wiki_dir / "docker.md").write_text(
        "# Docker Concept\n\nBody text.\n", encoding="utf-8"
    )
    r = await api_client.get("/api/graph/wiki/docker")
    assert r.status_code == 200
    data = r.json()
    assert data["slug"] == "docker"
    assert data["title"] == "Docker Concept"
    assert "Body text." in data["markdown"]


async def test_article_404_when_missing(api_client, wiki_dir):
    r = await api_client.get("/api/graph/wiki/nonexistent")
    assert r.status_code == 404


# Note: HTTP-layer traversal tests live at the service level (see
# tests/services/test_graph_service.py::test_safe_wiki_path_rejects_traversal_with_parent).
# httpx's ASGITransport URL-decodes %2F → / in scope['path'] before routing,
# which splits the slug into additional segments and never reaches the
# /api/graph/wiki/{slug} handler. Real HTTP clients preserve %2F and hit the
# handler with slug='../SECRET', where _safe_wiki_path rejects it via
# relative_to → ValueError. The service-layer test is the system of record.


# ---------------------------------------------------------------------------
# /api/graph/wiki/lookup
# ---------------------------------------------------------------------------

async def test_lookup_god_node_precedence(api_client, wiki_dir, db_session):
    """When both a god-node article and a community article exist for a
    concept, the god-node slug wins.
    """
    from models import Concept

    (wiki_dir / "docker.md").write_text("# docker\n", encoding="utf-8")
    (wiki_dir / "Community_2.md").write_text("# Community 2\n", encoding="utf-8")
    db_session.add(Concept(id="concept_docker", name="docker", community_id=2, degree=10))
    await db_session.commit()

    r = await api_client.get(
        "/api/graph/wiki/lookup?concept_id=concept_docker&concept_name=docker"
    )
    assert r.status_code == 200
    assert r.json() == {"slug": "docker"}


async def test_lookup_community_fallback(api_client, wiki_dir, db_session):
    """No god-node article for the given name → fall back to community slug."""
    from models import Concept

    (wiki_dir / "Community_3.md").write_text("# Community 3\n", encoding="utf-8")
    db_session.add(Concept(id="c1", name="unknownname", community_id=3, degree=2))
    await db_session.commit()

    r = await api_client.get(
        "/api/graph/wiki/lookup?concept_id=c1&concept_name=unknownname"
    )
    assert r.status_code == 200
    assert r.json() == {"slug": "Community_3"}


async def test_lookup_no_params_404(api_client, wiki_dir):
    r = await api_client.get("/api/graph/wiki/lookup")
    assert r.status_code == 404


async def test_lookup_name_only_no_match(api_client, wiki_dir):
    """concept_name present but no matching god-node file → 404."""
    r = await api_client.get("/api/graph/wiki/lookup?concept_name=missing")
    assert r.status_code == 404


async def test_lookup_concept_id_unknown(api_client, wiki_dir):
    """concept_id not in DB → community lookup fails → 404."""
    r = await api_client.get("/api/graph/wiki/lookup?concept_id=does_not_exist")
    assert r.status_code == 404


async def test_lookup_concept_id_null_community(api_client, wiki_dir, db_session):
    """Concept row exists but has community_id=NULL → 404."""
    from models import Concept

    db_session.add(Concept(id="orphan", name="orphan", community_id=None, degree=0))
    await db_session.commit()

    r = await api_client.get("/api/graph/wiki/lookup?concept_id=orphan")
    assert r.status_code == 404


async def test_lookup_concept_id_community_file_missing(
    api_client, wiki_dir, db_session
):
    """Concept has community_id but the community article file doesn't exist → 404."""
    from models import Concept

    db_session.add(Concept(id="c2", name="x", community_id=99, degree=1))
    await db_session.commit()

    r = await api_client.get("/api/graph/wiki/lookup?concept_id=c2")
    assert r.status_code == 404
