from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Concept
from services import dashboard_service as _dashboard


class GraphService:
    """File-pipeline operations for the Graphify knowledge graph.

    Owns the trigger/progress/status file protocol the host-side watcher uses
    and the on-demand import from `graph.json` into Postgres.

    ``GRAPHIFY_OUT`` is read via ``_dashboard.GRAPHIFY_OUT`` at call time so
    monkeypatching ``services.dashboard_service.GRAPHIFY_OUT`` in tests takes
    effect without a second patch target.
    """

    _WIKI_LINK_RE = re.compile(r"\[\[([^\[\]]+)\]\]")

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_status(self) -> dict:
        count_result = await self.db.execute(select(func.count(Concept.id)))
        has_data = count_result.scalar_one() > 0

        root = _dashboard.GRAPHIFY_OUT
        status_file = root / ".status"
        graph_file = root / "graph.json"
        trigger_file = root / ".generate_requested"

        if trigger_file.exists():
            status = "generating"
        elif status_file.exists():
            status = status_file.read_text(encoding="utf-8").strip()
        elif graph_file.exists():
            status = "ready"
        else:
            status = "none"

        progress = None
        if status == "generating":
            progress_file = root / ".progress"
            if progress_file.exists():
                try:
                    progress = json.loads(progress_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
            if progress is None:
                progress = {"done": 0, "total": 0, "current": None, "ok": 0, "failed": 0, "model": ""}

        return {"status": status, "has_data": has_data, "progress": progress}

    async def trigger_regeneration(self) -> dict:
        """Write trigger + status files; the host-side watcher picks them up."""
        root = _dashboard.GRAPHIFY_OUT
        root.mkdir(parents=True, exist_ok=True)
        (root / ".generate_requested").write_text("1", encoding="utf-8")
        (root / ".status").write_text("generating", encoding="utf-8")
        return {"status": "generating"}

    async def import_from_disk(self) -> dict:
        graph_file = _dashboard.GRAPHIFY_OUT / "graph.json"
        if not graph_file.exists():
            return {"ok": False, "error": "No graph.json found"}
        try:
            from import_graph import import_graph

            await import_graph(str(graph_file))
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -----------------------------------------------------------------------
    # Wiki surface (Phase 8) — community + god-node articles written to disk
    # by `graphify.wiki.to_wiki` during extraction.
    # -----------------------------------------------------------------------

    @staticmethod
    def _wiki_slug(label: str) -> str:
        """Replicate graphify.wiki._safe_filename exactly.

        Three literal substitutions; locked by the parity test in
        tests/services/test_graph_service.py.
        """
        return label.replace("/", "-").replace(" ", "_").replace(":", "-")

    def _safe_wiki_path(self, slug: str) -> Path | None:
        """Return the resolved path to `wiki/{slug}.md` if it exists and
        stays inside the wiki root. Any traversal attempt returns None.
        """
        root = _dashboard.GRAPHIFY_OUT / "wiki"
        if not root.exists():
            return None
        root_resolved = root.resolve()
        target = (root / f"{slug}.md").resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError:
            return None
        if not target.is_file():
            return None
        return target

    def _parse_index_articles(self, md: str) -> list[dict]:
        """Extract (slug, title, kind) triples from the index.md sections.

        Treats every line under a `## Communities` header as community
        articles, every line under a `## God Nodes` header as god-node
        articles, until the next `## ` heading or the end of the file.
        Deduplicates by slug (first occurrence wins).
        """
        articles: list[dict] = []
        current_kind: str | None = None
        for line in md.split("\n"):
            stripped = line.strip()
            if stripped.startswith("## "):
                heading = stripped[3:].strip().lower()
                if heading.startswith("communit"):
                    current_kind = "community"
                elif heading.startswith("god node"):
                    current_kind = "god_node"
                else:
                    current_kind = None
                continue
            if current_kind is None:
                continue
            for match in self._WIKI_LINK_RE.finditer(stripped):
                label = match.group(1).strip()
                if not label or label.lower() == "index":
                    continue
                articles.append(
                    {"slug": self._wiki_slug(label), "title": label, "kind": current_kind}
                )
        seen: set[str] = set()
        deduped: list[dict] = []
        for a in articles:
            if a["slug"] in seen:
                continue
            seen.add(a["slug"])
            deduped.append(a)
        return deduped

    @staticmethod
    def _extract_title(md: str, fallback: str) -> str:
        for line in md.split("\n"):
            if line.startswith("# "):
                return line[2:].strip() or fallback
        return fallback

    async def load_wiki_index(self) -> dict | None:
        """Return {title, markdown, articles} for `wiki/index.md`, or None."""
        path = _dashboard.GRAPHIFY_OUT / "wiki" / "index.md"
        if not path.exists() or not path.is_file():
            return None
        md = path.read_text(encoding="utf-8")
        return {
            "title": self._extract_title(md, "Knowledge Graph Index"),
            "markdown": md,
            "articles": self._parse_index_articles(md),
        }

    async def load_wiki_article(self, slug: str) -> dict | None:
        """Return {slug, title, markdown} for the named article, or None."""
        target = self._safe_wiki_path(slug)
        if target is None:
            return None
        md = target.read_text(encoding="utf-8")
        return {"slug": slug, "title": self._extract_title(md, slug), "markdown": md}

    async def resolve_wiki_slug(
        self, concept_id: str | None, concept_name: str | None
    ) -> str | None:
        """Resolve a graph node to its wiki slug.

        Precedence:
          1. God-node article by display name (`concept_name`).
          2. Community article via `concepts.community_id` lookup on `concept_id`.
          3. None → route layer returns 404.
        """
        if concept_name:
            candidate = self._wiki_slug(concept_name)
            if self._safe_wiki_path(candidate) is not None:
                return candidate
        if concept_id:
            result = await self.db.execute(
                select(Concept.community_id).where(Concept.id == concept_id)
            )
            community_id = result.scalar_one_or_none()
            if community_id is not None:
                candidate = self._wiki_slug(f"Community {community_id}")
                if self._safe_wiki_path(candidate) is not None:
                    return candidate
        return None
