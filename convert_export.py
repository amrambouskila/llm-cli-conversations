#!/usr/bin/env python3
"""
Cross-platform wrapper for JSONL-to-Markdown conversion.

Replaces the bash-only convert_jsonl_to_md.sh with a Python script
that works on macOS, Linux, and Windows.

Usage:
  python convert_export.py                # export all projects
  python convert_export.py --list         # list available projects
  python convert_export.py project-name   # export matching project(s)
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_claude_config_dir() -> Path:
    """Get the Claude config directory, respecting CLAUDE_CONFIG_DIR env var."""
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".claude"


def get_projects_source() -> Path:
    """Get the Claude projects source directory."""
    return get_claude_config_dir() / "projects"


def get_export_root() -> Path:
    """Get the export root directory (where this script lives)."""
    return Path(__file__).resolve().parent


def sync_directory(src: Path, dst: Path) -> None:
    """Cross-platform directory sync (like rsync -a).

    Copies new and updated files from src to dst, preserving structure.
    Does not delete files in dst that don't exist in src (safe incremental).
    """
    if not src.exists():
        return

    dst.mkdir(parents=True, exist_ok=True)

    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            dst_file = dst / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            # Copy if destination doesn't exist or source is newer
            if not dst_file.exists():
                shutil.copy2(item, dst_file)
            else:
                src_mtime = item.stat().st_mtime
                dst_mtime = dst_file.stat().st_mtime
                if src_mtime > dst_mtime:
                    shutil.copy2(item, dst_file)


def list_projects(projects_src: Path) -> list[str]:
    """List available project directories."""
    if not projects_src.exists():
        return []
    return sorted(
        d.name for d in projects_src.iterdir() if d.is_dir()
    )


def count_jsonl_files(directory: Path) -> int:
    """Count .jsonl files in a directory (non-recursive top level)."""
    return len(list(directory.glob("*.jsonl")))


def main():
    export_root = get_export_root()
    projects_src = get_projects_source()

    # Check source exists
    if not projects_src.exists():
        print(f"ERROR: Claude projects directory not found: {projects_src}")
        print(f"       Expected at: {projects_src}")
        if platform.system() == "Windows":
            print(f"       On Windows, set CLAUDE_CONFIG_DIR if Claude uses a custom location.")
        sys.exit(1)

    available = list_projects(projects_src)
    if not available:
        print(f"ERROR: No project directories found in {projects_src}")
        sys.exit(1)

    # Handle --list
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        print(f"Available projects in {projects_src}:")
        for name in available:
            jsonl_count = count_jsonl_files(projects_src / name)
            print(f"  {name} ({jsonl_count} conversations)")
        sys.exit(0)

    # Handle filter
    filter_str = sys.argv[1] if len(sys.argv) > 1 else ""
    if filter_str:
        matched = [p for p in available if filter_str.lower() in p.lower()]
        if not matched:
            print(f'ERROR: No projects match "{filter_str}"')
            print(f"\nAvailable projects:")
            for name in available:
                print(f"  {name}")
            sys.exit(1)
        print(f'==> Filter: exporting projects matching "{filter_str}"')
        print(f"    Matched: {', '.join(matched)}")
    else:
        matched = available
        print("==> Exporting all projects")

    # Sync raw JSONL files
    raw_projects_dir = export_root / "raw" / "projects"
    raw_projects_dir.mkdir(parents=True, exist_ok=True)

    print("\n==> Syncing raw conversation data...")
    for project_name in matched:
        src = projects_src / project_name
        dst = raw_projects_dir / project_name
        jsonl_count = count_jsonl_files(src)
        print(f"    {project_name} ({jsonl_count} conversations)")
        sync_directory(src, dst)

    # Build manifest
    print("\n==> Building manifest...")
    manifest_path = export_root / "raw" / "manifest.txt"
    jsonl_files = sorted(str(f) for f in raw_projects_dir.rglob("*.jsonl"))
    manifest_path.write_text("\n".join(jsonl_files) + "\n", encoding="utf-8")
    print(f"    {len(jsonl_files)} total .jsonl files in manifest")

    # Convert to Markdown
    print("\n==> Converting JSONL to Markdown (one file per project)...")
    converter_script = export_root / "convert_claude_jsonl_to_md.py"
    if not converter_script.exists():
        print(f"ERROR: Converter script not found: {converter_script}")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(converter_script), str(raw_projects_dir), str(export_root / "markdown")],
        cwd=str(export_root),
    )

    if result.returncode != 0:
        print("ERROR: Conversion failed.")
        sys.exit(1)

    markdown_dir = export_root / "markdown"
    md_files = list(markdown_dir.glob("*.md"))
    print(f"\n==> All done. {len(md_files)} markdown files in: {markdown_dir}")
    print("    Each project is a single .md file with conversations ordered chronologically.")


if __name__ == "__main__":
    main()
