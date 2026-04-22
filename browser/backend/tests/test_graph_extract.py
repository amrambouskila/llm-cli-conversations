"""Unit tests for graph_extract — Phase 8 additions (file_type normalization,
god-node derivation, wiki wiring in build_graph)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# graph_extract.py lives at the project root; the backend is one level in.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import graph_extract  # noqa: E402, I001  — sys.path must be mutated before this import


# ---------------------------------------------------------------------------
# _normalize_file_type
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value",
    ["code", "document", "image", "paper", "rationale"],
)
def test_normalize_canonical_passes_through(value):
    assert graph_extract._normalize_file_type(value) == value


def test_normalize_is_case_insensitive():
    assert graph_extract._normalize_file_type("CODE") == "code"
    assert graph_extract._normalize_file_type("Document") == "document"


@pytest.mark.parametrize(
    "alias,canonical",
    [
        ("library", "code"),
        ("package", "code"),
        ("module", "code"),
        ("framework", "code"),
        ("markdown", "document"),
        ("readme", "document"),
        ("article", "paper"),
        ("pdf", "paper"),
        ("screenshot", "image"),
        ("diagram", "image"),
        ("decision", "rationale"),
        ("plan", "rationale"),
    ],
)
def test_normalize_alias(alias, canonical):
    assert graph_extract._normalize_file_type(alias) == canonical


def test_normalize_unknown_falls_back_to_code():
    assert graph_extract._normalize_file_type("totally-made-up") == "code"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_normalize_empty_values_fall_back_to_code(value):
    assert graph_extract._normalize_file_type(value) == "code"


# ---------------------------------------------------------------------------
# SYSTEM_PROMPT mentions the 5 allowed values
# ---------------------------------------------------------------------------

def test_system_prompt_enumerates_allowed_types():
    for allowed in ("code", "document", "image", "paper", "rationale"):
        assert allowed in graph_extract.SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# _derive_god_nodes
# ---------------------------------------------------------------------------

def test_derive_god_nodes_returns_top_by_degree():
    import networkx as nx

    G = nx.Graph()  # noqa: N806 — networkx convention names graphs `G`
    G.add_node("hub", label="Hub")
    for i in range(20):
        G.add_node(f"leaf{i}", label=f"Leaf{i}")
        G.add_edge("hub", f"leaf{i}")

    god = graph_extract._derive_god_nodes(G)
    assert len(god) == graph_extract.GOD_NODE_COUNT == 15
    assert god[0]["id"] == "hub"
    assert god[0]["label"] == "Hub"
    assert god[0]["edges"] == 20
    assert god[0]["degree"] == 20
    for entry in god[1:]:
        assert entry["edges"] == 1
        assert entry["degree"] == 1


def test_derive_god_nodes_label_fallback_to_id():
    import networkx as nx

    G = nx.Graph()  # noqa: N806 — networkx convention names graphs `G`
    G.add_node("bare")
    G.add_edge("bare", "other")
    G.add_node("other")

    god = graph_extract._derive_god_nodes(G)
    bare = next(entry for entry in god if entry["id"] == "bare")
    assert bare["label"] == "bare"


# ---------------------------------------------------------------------------
# build_graph — wiki wiring + file_type normalization
# ---------------------------------------------------------------------------

def _write_chunk(out_dir: Path, name: str, nodes: list[dict], edges: list[dict]) -> None:
    (out_dir / f".graphify_chunk_{name}.json").write_text(
        json.dumps({"nodes": nodes, "edges": edges}), encoding="utf-8"
    )


def test_build_graph_writes_wiki_directory(tmp_path):
    _write_chunk(
        tmp_path,
        "t",
        nodes=[
            {"id": "a", "label": "A", "file_type": "code"},
            {"id": "b", "label": "B", "file_type": "document"},
            {"id": "c", "label": "C", "file_type": "code"},
        ],
        edges=[
            {"source": "a", "target": "b", "relation": "uses", "weight": 1.0,
             "confidence": "EXTRACTED", "confidence_score": 1.0},
            {"source": "b", "target": "c", "relation": "uses", "weight": 1.0,
             "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )

    assert graph_extract.build_graph(tmp_path) is True
    assert (tmp_path / "graph.json").is_file()
    wiki_dir = tmp_path / "wiki"
    assert wiki_dir.is_dir()
    assert (wiki_dir / "index.md").is_file()


def test_build_graph_normalizes_file_types_before_build(tmp_path, monkeypatch):
    """Aliases like 'library' get rewritten to 'code' before hitting build_from_json."""
    _write_chunk(
        tmp_path,
        "t",
        nodes=[
            {"id": "x", "label": "X", "file_type": "library"},
            {"id": "y", "label": "Y", "file_type": "widget"},  # unknown → code
            {"id": "z", "label": "Z", "file_type": "screenshot"},  # alias → image
        ],
        edges=[
            {"source": "x", "target": "y", "relation": "uses", "weight": 1.0,
             "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )

    captured: list[dict] = []
    import graphify.build as graphify_build

    real_build = graphify_build.build_from_json

    def capturing_build(extraction):
        captured.append(extraction)
        return real_build(extraction)

    monkeypatch.setattr(graphify_build, "build_from_json", capturing_build)

    assert graph_extract.build_graph(tmp_path) is True
    assert len(captured) == 1
    types = {n["id"]: n["file_type"] for n in captured[0]["nodes"]}
    assert types == {"x": "code", "y": "code", "z": "image"}


def test_build_graph_returns_false_on_no_nodes(tmp_path):
    _write_chunk(tmp_path, "empty", nodes=[], edges=[])
    assert graph_extract.build_graph(tmp_path) is False


def test_build_graph_tolerates_corrupt_chunk(tmp_path):
    """A chunk file with invalid JSON is skipped with a warning, not fatal."""
    (tmp_path / ".graphify_chunk_broken.json").write_text(
        "{not json", encoding="utf-8"
    )
    _write_chunk(
        tmp_path,
        "good",
        nodes=[
            {"id": "a", "label": "A", "file_type": "code"},
            {"id": "b", "label": "B", "file_type": "code"},
        ],
        edges=[
            {"source": "a", "target": "b", "relation": "uses", "weight": 1.0,
             "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )
    assert graph_extract.build_graph(tmp_path) is True


def test_build_graph_skips_duplicate_node_ids(tmp_path):
    _write_chunk(
        tmp_path,
        "a",
        nodes=[{"id": "same", "label": "First", "file_type": "code"}],
        edges=[],
    )
    _write_chunk(
        tmp_path,
        "b",
        nodes=[
            {"id": "same", "label": "Second", "file_type": "code"},
            {"id": "other", "label": "Other", "file_type": "code"},
        ],
        edges=[
            {"source": "same", "target": "other", "relation": "uses", "weight": 1.0,
             "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )

    assert graph_extract.build_graph(tmp_path) is True
    graph = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    ids = [n["id"] for n in graph.get("nodes", [])]
    assert ids.count("same") == 1


def test_build_graph_handles_missing_node_id(tmp_path):
    """Chunks may contain nodes with no 'id' — they must be skipped cleanly."""
    _write_chunk(
        tmp_path,
        "t",
        nodes=[
            {"label": "Nameless", "file_type": "code"},  # no id
            {"id": "kept", "label": "Kept", "file_type": "code"},
            {"id": "other", "label": "Other", "file_type": "code"},
        ],
        edges=[
            {"source": "kept", "target": "other", "relation": "uses", "weight": 1.0,
             "confidence": "EXTRACTED", "confidence_score": 1.0},
        ],
    )
    assert graph_extract.build_graph(tmp_path) is True


def test_build_graph_without_graphify_returns_false(tmp_path, monkeypatch):
    """If the graphify import fails, build_graph logs and returns False."""
    import builtins

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if name.startswith("graphify"):
            raise ImportError(f"simulated missing {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    assert graph_extract.build_graph(tmp_path) is False
