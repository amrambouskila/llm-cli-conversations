"""Extract concept graph from conversation markdown files using claude CLI.

Called by the graph watcher in export_service.sh / graph_watcher.bat.
Reads markdown files, condenses them to just user requests and conversation
headers (stripping tool output, code blocks, assistant responses), then
calls claude -p with --system-prompt for semantic extraction.

Progress is written to graphify-out/.progress for the frontend to poll.
Completed extractions are cached in graphify-out/.graphify_chunk_*.json
so subsequent runs skip already-extracted files.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _log(msg: str, err: bool = False) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr if err else sys.stdout, flush=True)


GRAPHIFY_MODEL = os.environ.get("GRAPHIFY_MODEL", "claude-sonnet-4-6")
MAX_CONDENSED_CHARS = 120_000

# System prompt is architecturally separated from user content via --system-prompt.
# This prevents Claude from treating conversation markdown as a conversation to continue.
SYSTEM_PROMPT = (
    "You are a structured data extraction tool. "
    "You will receive a condensed conversation log containing user requests and headers. "
    "DO NOT continue, summarize, reply to, or engage with the content. "
    "DO NOT treat it as a conversation to respond to. "
    "Your ONLY job is to extract a knowledge graph as valid JSON. "
    "Output ONLY raw JSON with no markdown fences, no explanation, no preamble, no text before or after the JSON."
)

USER_PROMPT_TEMPLATE = (
    "Extract a knowledge graph from the condensed conversation log below. "
    "Identify named concepts, tools, technologies, libraries, projects, patterns, and decisions. "
    "For each pair of related concepts, add an edge.\n\n"
    "Output ONLY this JSON structure:\n"
    '{{"nodes":[{{"id":"short_snake_id","label":"Human Name","file_type":"document",'
    '"source_file":"FILEPATH"}}],"edges":[{{"source":"id1","target":"id2",'
    '"relation":"uses|references|discusses|depends_on",'
    '"confidence":"EXTRACTED","confidence_score":1.0,'
    '"source_file":"FILEPATH","weight":1.0}}]}}\n\n'
    "=== DOCUMENT ===\n"
)


def condense_markdown(content: str) -> str:
    """Strip conversation markdown to just user requests and conversation headers.

    Removes assistant responses, tool output, code blocks, entry key comments,
    metadata lines (UUIDs, booleans, tool deltas). Keeps the first ~300 chars
    of each user request for context.

    Typical reduction: 95-99% (29MB -> 500KB, 724KB -> 7KB).
    """
    lines = content.split("\n")
    condensed = []
    in_user = False
    user_chars = 0

    for line in lines:
        # Keep top-level and conversation headers
        if line.startswith("## Conversation") or line.startswith("# "):
            condensed.append(line)
            in_user = False
            continue
        # Keep user request markers and first ~300 chars of each request
        if ">>>USER_REQUEST<<<" in line:
            condensed.append(line)
            in_user = True
            user_chars = 0
            continue
        if in_user:
            user_chars += len(line)
            if user_chars < 300:
                condensed.append(line)
            elif user_chars < 310:
                condensed.append("...")
                in_user = False
            continue
        # Skip everything else (assistant responses, tool output, code, metadata)

    return "\n".join(condensed)


def strip_fences(text: str) -> str:
    """Remove markdown code fences from claude's response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def parse_graph_json(raw: str) -> dict | None:
    """Try multiple strategies to extract {nodes, edges} JSON from raw output."""
    cleaned = strip_fences(raw.strip())

    # Direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "nodes" in data and "edges" in data:
            return data
        # --output-format json wrapper: {"result": "..."}
        if isinstance(data, dict) and "result" in data:
            inner = data["result"]
            if isinstance(inner, dict) and "nodes" in inner:
                return inner
            if isinstance(inner, str):
                return parse_graph_json(inner)
    except (json.JSONDecodeError, TypeError):
        pass

    # Find JSON object in the response
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, dict) and "nodes" in data and "edges" in data:
                return data
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def extract_file(md_path: Path, out_dir: Path, model: str) -> bool:
    """Extract concepts from a single markdown file. Returns True on success."""
    stem = md_path.stem
    chunk_file = out_dir / f".graphify_chunk_{stem}.json"

    if chunk_file.exists():
        return True

    basename = md_path.name
    user_prompt = USER_PROMPT_TEMPLATE.replace("FILEPATH", basename)

    content = md_path.read_text(encoding="utf-8", errors="replace")

    # Small files (<500KB) are sent raw — condensation strips user message
    # text from short conversations, leaving only structural scaffolding.
    if len(content) < 512_000:
        body = content
    else:
        body = condense_markdown(content)

    if len(body) > MAX_CONDENSED_CHARS:
        body = body[:MAX_CONDENSED_CHARS]

    if len(body.strip()) < 50:
        _log(f"  SKIP (no user content): {basename}", err=True)
        return False

    stdin_text = f"{user_prompt}{body}"

    try:
        result = subprocess.run(
            [
                "claude", "-p",
                "--model", model,
                "--system-prompt", SYSTEM_PROMPT,
            ],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        _log("  ERROR: claude CLI not found", err=True)
        return False
    except subprocess.TimeoutExpired:
        _log(f"  TIMEOUT: {basename}", err=True)
        return False

    if result.returncode != 0:
        _log(f"  FAILED: {basename} (exit {result.returncode})", err=True)
        if result.stderr:
            _log(f"    {result.stderr[:200]}", err=True)
        return False

    raw = result.stdout
    if not raw.strip():
        _log(f"  EMPTY: {basename}", err=True)
        return False

    data = parse_graph_json(raw)
    if data:
        chunk_file.write_text(json.dumps(data), encoding="utf-8")
        _log(f"  OK: {basename} ({len(data['nodes'])} nodes, {len(data['edges'])} edges)")
        return True

    _log(f"  NO VALID JSON: {basename}", err=True)
    _log(f"    Response ({len(raw)} chars) starts with: {raw[:200]}", err=True)
    return False


def build_graph(out_dir: Path) -> bool:
    """Merge all chunk extractions and build the final graph."""
    try:
        from graphify.build import build_from_json
        from graphify.cluster import cluster
        from graphify.export import to_json
    except ImportError:
        _log("ERROR: graphifyy not installed (pip install graphifyy)", err=True)
        return False

    all_nodes = []
    all_edges = []
    seen_ids = set()

    for chunk_file in sorted(out_dir.glob(".graphify_chunk_*.json")):
        try:
            data = json.loads(chunk_file.read_text(encoding="utf-8"))
            for node in data.get("nodes", []):
                nid = node.get("id")
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    all_nodes.append(node)
            all_edges.extend(data.get("edges", []))
        except Exception as e:
            _log(f"  Warning: {chunk_file.name}: {e}", err=True)

    if not all_nodes:
        _log("  No nodes extracted — cannot build graph", err=True)
        return False

    extraction = {
        "nodes": all_nodes,
        "edges": all_edges,
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }

    G = build_from_json(extraction)
    communities = cluster(G)
    to_json(G, communities, str(out_dir / "graph.json"))

    _log(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities")
    return True


def write_status(out_dir: Path, status: str) -> None:
    (out_dir / ".status").write_text(status, encoding="utf-8")


def write_progress(out_dir: Path, done: int, total: int, current: str, ok: int, failed: int) -> None:
    progress = {
        "done": done,
        "total": total,
        "current": current,
        "ok": ok,
        "failed": failed,
        "model": GRAPHIFY_MODEL,
    }
    (out_dir / ".progress").write_text(json.dumps(progress), encoding="utf-8")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    markdown_dir = script_dir / "markdown"
    codex_dir = script_dir / "markdown_codex"
    out_dir = Path(os.environ.get("GRAPHIFY_OUT", str(script_dir / "graphify-out")))
    out_dir.mkdir(parents=True, exist_ok=True)

    md_files = []
    for d in (markdown_dir, codex_dir):
        if d.exists():
            md_files.extend(sorted(d.glob("*.md")))

    if not md_files:
        _log("No markdown files found.", err=True)
        write_status(out_dir, "error")
        sys.exit(1)

    _log(f"[graph] Extracting concepts from {len(md_files)} files (model: {GRAPHIFY_MODEL})")
    write_status(out_dir, "generating")

    ok = 0
    failed = 0
    for i, md_file in enumerate(md_files):
        _log(f"  [{i + 1}/{len(md_files)}] {md_file.name}...")
        write_progress(out_dir, i, len(md_files), md_file.stem, ok, failed)

        if extract_file(md_file, out_dir, GRAPHIFY_MODEL):
            ok += 1
        else:
            failed += 1

    write_progress(out_dir, len(md_files), len(md_files), "", ok, failed)
    _log(f"[graph] Extraction: {ok} ok, {failed} failed")

    if ok == 0:
        _log("[graph] No successful extractions", err=True)
        write_status(out_dir, "error")
        sys.exit(1)

    _log("[graph] Building graph...")
    if build_graph(out_dir):
        write_status(out_dir, "ready")
        _log("[graph] Done — graph.json written")
    else:
        write_status(out_dir, "error")
        sys.exit(1)


if __name__ == "__main__":
    main()
