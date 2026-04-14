"""
FastAPI backend for browsing LLM CLI exported conversations.

Serves:
  - REST API at /api/*
  - React static build at / (in production / Docker)

Runs locally with no internet dependency for core browsing.
"""

import asyncio
import os
import shutil
import subprocess
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routes import projects, segments, conversations, stats, summaries, visibility, dashboard

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent

DEFAULT_MARKDOWN_DIR = os.environ.get(
    "MARKDOWN_DIR",
    str(SCRIPT_DIR.parent.parent / "markdown"),
)
STATIC_DIR = os.environ.get(
    "STATIC_DIR",
    str(SCRIPT_DIR.parent / "frontend" / "dist"),
)
CLAUDE_PROJECTS_SRC = os.environ.get(
    "CLAUDE_PROJECTS_SRC",
    str(Path.home() / ".claude" / "projects"),
)
RAW_DIR = os.environ.get(
    "RAW_DIR",
    str(SCRIPT_DIR.parent.parent / "raw"),
)

# Codex paths
CODEX_SESSIONS_SRC = os.environ.get(
    "CODEX_SESSIONS_SRC",
    str(Path.home() / ".codex" / "sessions"),
)
CODEX_MARKDOWN_DIR = os.environ.get(
    "CODEX_MARKDOWN_DIR",
    str(Path(DEFAULT_MARKDOWN_DIR).parent / "markdown_codex"),
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
startup_ready = False


async def _startup_load():
    global startup_ready
    try:
        from load import load_all
        raw_projects = str(Path(RAW_DIR) / "projects")
        results = await load_all(
            DEFAULT_MARKDOWN_DIR,
            CODEX_MARKDOWN_DIR,
            raw_projects,
            CODEX_SESSIONS_SRC,
        )
        _log(f"Startup Postgres load: {results}")
    except Exception as e:
        _log(f"Startup Postgres load failed (non-fatal): {e}")
    startup_ready = True
    _log("Backend ready — serving data")


@asynccontextmanager
async def lifespan(app):
    from db import init_db
    await init_db()
    _log("Database schema initialized (conversations.*)")

    # Load data in background so the app serves requests immediately
    asyncio.create_task(_startup_load())
    yield

app = FastAPI(title="LLM Conversation Browser", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://localhost:5050", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(projects.router)
app.include_router(segments.router)
app.include_router(conversations.router)
app.include_router(stats.router)
app.include_router(summaries.router)
app.include_router(visibility.router)
app.include_router(dashboard.router)


# ---------------------------------------------------------------------------
# Helpers for the update pipeline
# ---------------------------------------------------------------------------
def sync_directory(src: Path, dst: Path) -> None:
    """Copy new/updated files from src to dst, preserving structure."""
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            dst_file = dst / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            if not dst_file.exists():
                shutil.copy2(item, dst_file)
            elif item.stat().st_mtime > dst_file.stat().st_mtime:
                shutil.copy2(item, dst_file)


async def run_export_pipeline() -> dict:
    """Run the full sync + convert pipeline and return a status dict."""
    projects_src = Path(CLAUDE_PROJECTS_SRC)
    raw_dir = Path(RAW_DIR)
    raw_projects_dir = raw_dir / "projects"
    markdown_dir = Path(DEFAULT_MARKDOWN_DIR)
    converter_script = SCRIPT_DIR / "convert_claude_jsonl_to_md.py"

    log_lines = []

    if not projects_src.exists():
        return {
            "success": False,
            "error": f"Claude projects directory not found: {projects_src}",
            "log": [],
        }

    project_dirs = sorted(d for d in projects_src.iterdir() if d.is_dir())
    if not project_dirs:
        return {
            "success": False,
            "error": "No project directories found in source.",
            "log": [],
        }

    log_lines.append(f"Found {len(project_dirs)} projects in {projects_src}")

    raw_projects_dir.mkdir(parents=True, exist_ok=True)
    for pd in project_dirs:
        jsonl_count = len(list(pd.glob("*.jsonl")))
        log_lines.append(f"  Syncing {pd.name} ({jsonl_count} conversations)")
        sync_directory(pd, raw_projects_dir / pd.name)

    manifest_path = raw_dir / "manifest.txt"
    jsonl_files = sorted(str(f) for f in raw_projects_dir.rglob("*.jsonl"))
    manifest_path.write_text("\n".join(jsonl_files) + "\n", encoding="utf-8")
    log_lines.append(f"Manifest: {len(jsonl_files)} .jsonl files")

    # Wipe existing markdown files before re-converting to prevent
    # duplicates from different naming schemes (host vs Docker home paths)
    markdown_dir.mkdir(parents=True, exist_ok=True)
    for old_md in markdown_dir.glob("*.md"):
        old_md.unlink()

    result = subprocess.run(
        [sys.executable, str(converter_script), str(raw_projects_dir), str(markdown_dir)],
        capture_output=True,
        text=True,
    )
    if result.stdout:
        log_lines.extend(result.stdout.strip().split("\n"))
    if result.returncode != 0:
        err = result.stderr.strip() if result.stderr else "unknown error"
        return {
            "success": False,
            "error": f"Conversion failed: {err}",
            "log": log_lines,
        }

    # Also convert Codex sessions if available
    codex_converter = SCRIPT_DIR / "convert_codex_sessions.py"
    codex_src = Path(CODEX_SESSIONS_SRC)
    codex_md = Path(CODEX_MARKDOWN_DIR)
    if codex_src.exists() and codex_converter.exists():
        codex_md.mkdir(parents=True, exist_ok=True)
        for old_md in codex_md.glob("*.md"):
            old_md.unlink()
        cx_result = subprocess.run(
            [sys.executable, str(codex_converter), str(codex_src), str(codex_md)],
            capture_output=True, text=True,
        )
        if cx_result.stdout:
            log_lines.extend(cx_result.stdout.strip().split("\n"))

    # Sync Postgres with the freshly converted markdown
    pg_results: dict = {}
    try:
        from load import load_all
        pg_results = await load_all(
            str(markdown_dir),
            str(codex_md),
            str(raw_projects_dir),
            CODEX_SESSIONS_SRC,
        )
        log_lines.append(f"Postgres loaded: {pg_results}")
    except Exception as e:
        log_lines.append(f"Postgres load failed (non-fatal): {e}")

    return {
        "success": True,
        "sessions": sum(pg_results.values()) if pg_results else 0,
        "log": log_lines,
    }


# ---------------------------------------------------------------------------
# API routes that stay in app.py
# ---------------------------------------------------------------------------
@app.get("/api/ready")
async def api_ready():
    return {"ready": startup_ready}


@app.post("/api/update")
async def api_update():
    """Run the full export pipeline: sync, convert, re-index."""
    try:
        result = await run_export_pipeline()
        status_code = 200 if result["success"] else 500
        return JSONResponse(result, status_code=status_code)
    except Exception as e:
        return JSONResponse(
            {"success": False, "error": str(e), "log": traceback.format_exc().split("\n")},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# Serve React static build (production / Docker)
# ---------------------------------------------------------------------------
static_path = Path(STATIC_DIR)
if static_path.exists() and (static_path / "index.html").exists():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    if (static_path / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(static_path / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = static_path / full_path
        # Guard against path traversal (defense-in-depth)
        if not str(file_path.resolve()).startswith(str(static_path.resolve())):
            return FileResponse(str(static_path / "index.html"))
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(static_path / "index.html"))