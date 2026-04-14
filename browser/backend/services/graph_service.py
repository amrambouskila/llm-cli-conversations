from __future__ import annotations

import json

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
