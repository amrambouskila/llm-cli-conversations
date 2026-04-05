"""
Parser module for LLM CLI exported Markdown conversations.

Reads Markdown files produced by convert_claude_jsonl_to_md.py or
convert_codex_sessions.py and splits them into structured data models
using >>>USER_REQUEST<<< as the primary delimiter.

Format discovered from actual files:
- Header: # ProjectName ... ---
- Conversation/session separator: ## Conversation `uuid` (started TIMESTAMP)
                                  ## Session `uuid` (started TIMESTAMP)
- Entry key: <!-- ENTRY_KEY: ... -->  (Claude format only)
- User request delimiter: >>>USER_REQUEST<<<  (on its own line, before # User #N heading)
- Headings: # User #N — TIMESTAMP — conv: `uuid`   (real user)
            ### Assistant #N — TIMESTAMP — conv: `uuid`
            ### Tool Output #N — TIMESTAMP — conv: `uuid`
- Tool calls: **Tool Call: `ToolName`** followed by ```json block
- Timestamps: ISO 8601, e.g. 2026-03-26T22:07:03.466Z
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Regex patterns derived from inspecting the real markdown output
# ---------------------------------------------------------------------------

# Matches: >>>USER_REQUEST<<<
USER_REQUEST_DELIM = re.compile(r"^>>>USER_REQUEST<<<\s*$", re.MULTILINE)

# Matches: # User #2 — 2026-03-26T22:07:03.466Z — conv: `uuid`
HEADING_RE = re.compile(
    r"^(#{1,3})\s+(User|Assistant|Tool Output|Entry|System)\s+#(\d+)"
    r"(?:\s+—\s+(\d{4}-\d{2}-\d{2}T[\d:.]+Z?))?"
    r"(?:\s+—\s+conv:\s+`([^`]+)`)?\s*$",
    re.MULTILINE,
)

# Matches: ## Conversation `uuid` (started TIMESTAMP)  or  ## Session `uuid` (started TIMESTAMP)
CONVERSATION_RE = re.compile(
    r"^##\s+(?:Conversation|Session)\s+`([^`]+)`\s+\(started\s+(.+?)\)\s*$",
    re.MULTILINE,
)

# Matches: **Tool Call: `ToolName`**
TOOL_CALL_RE = re.compile(r"\*\*Tool Call:\s*`([^`]+)`\*\*")

# Matches: <!-- ENTRY_KEY: ... -->
ENTRY_KEY_RE = re.compile(r"<!--\s*ENTRY_KEY:\s*(.+?)\s*-->")

# ISO timestamp
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Metrics:
    char_count: int = 0
    word_count: int = 0
    line_count: int = 0
    estimated_tokens: int = 0
    tool_call_count: int = 0


@dataclass
class RequestSegment:
    id: str = ""
    source_file: str = ""
    project_name: str = ""
    segment_index: int = 0
    raw_markdown: str = ""
    preview: str = ""
    timestamp: Optional[str] = None
    parsed_timestamp: Optional[datetime] = None
    conversation_id: Optional[str] = None
    entry_number: Optional[int] = None
    metrics: Metrics = field(default_factory=Metrics)


@dataclass
class ConversationFile:
    file_path: str = ""
    project_name: str = ""
    display_name: str = ""
    total_conversations: int = 0
    segments: list = field(default_factory=list)


@dataclass
class Project:
    name: str = ""
    display_name: str = ""
    files: list = field(default_factory=list)
    total_requests: int = 0


# ---------------------------------------------------------------------------
# Parsing functions
# ---------------------------------------------------------------------------

def compute_metrics(text: str) -> Metrics:
    """Compute metrics for a text segment."""
    lines = text.split("\n")
    words = text.split()
    tool_calls = TOOL_CALL_RE.findall(text)
    return Metrics(
        char_count=len(text),
        word_count=len(words),
        line_count=len(lines),
        # Rough approximation: ~4 chars per token for English + code
        estimated_tokens=max(1, len(text) // 4),
        tool_call_count=len(tool_calls),
    )


def compute_tool_breakdown(text: str) -> dict[str, int]:
    """Count occurrences of each tool name in the text."""
    tools = TOOL_CALL_RE.findall(text)
    breakdown: dict[str, int] = {}
    for name in tools:
        breakdown[name] = breakdown.get(name, 0) + 1
    return breakdown


def extract_preview(text: str, max_len: int = 120) -> str:
    """Extract a short preview from a request segment.

    Looks for the first real user text line after the heading.
    """
    lines = text.strip().split("\n")
    for line in lines:
        stripped = line.strip()
        # Skip empty, delimiters, HTML comments, headings
        if not stripped:
            continue
        if stripped.startswith(">>>"):
            continue
        if stripped.startswith("<!--"):
            continue
        if stripped.startswith("#"):
            # This is the heading line — extract user text from subsequent lines
            continue
        # Found actual content
        if len(stripped) > max_len:
            return stripped[:max_len] + "..."
        return stripped
    return "(empty request)"


def parse_timestamp_str(ts_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp string."""
    if not ts_str:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


def stable_id(source_file: str, segment_index: int) -> str:
    """Generate a stable ID for a segment."""
    raw = f"{source_file}:{segment_index}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def parse_markdown_file(file_path: str, project_name: str) -> ConversationFile:
    """Parse a single markdown file into a ConversationFile with RequestSegments."""
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")

    display_name = path.stem

    # Count conversations from header or conversation markers
    conv_matches = CONVERSATION_RE.findall(content)
    total_conversations = len(conv_matches)

    # Split on >>>USER_REQUEST<<<
    # Each segment after the first split is a user request + the assistant response
    # that follows until the next delimiter
    parts = USER_REQUEST_DELIM.split(content)

    conv_file = ConversationFile(
        file_path=str(path),
        project_name=project_name,
        display_name=display_name,
        total_conversations=total_conversations,
    )

    if len(parts) <= 1:
        # No user requests found — treat entire file as one segment
        seg = RequestSegment(
            id=stable_id(str(path), 0),
            source_file=str(path),
            project_name=project_name,
            segment_index=0,
            raw_markdown=content,
            preview=extract_preview(content),
            metrics=compute_metrics(content),
        )
        conv_file.segments.append(seg)
        return conv_file

    # parts[0] is the header/preamble before the first >>>USER_REQUEST<<<
    # parts[1:] are the actual request segments

    # Track current conversation context
    current_conv_id = None

    # Scan preamble for conversation ID
    preamble_conv = CONVERSATION_RE.findall(parts[0])
    if preamble_conv:
        current_conv_id = preamble_conv[-1][0]

    for idx, segment_text in enumerate(parts[1:]):
        seg_index = idx

        # Extract heading info (timestamp, conv id, entry number)
        heading_match = HEADING_RE.search(segment_text)
        timestamp = None
        entry_number = None
        conv_id = current_conv_id

        if heading_match:
            entry_number = int(heading_match.group(3))
            timestamp = heading_match.group(4)
            if heading_match.group(5):
                conv_id = heading_match.group(5)
                current_conv_id = conv_id

        # Also check for conversation markers within this segment
        conv_in_seg = CONVERSATION_RE.findall(segment_text)
        if conv_in_seg:
            current_conv_id = conv_in_seg[-1][0]

        # Fallback: look for any timestamp in the text
        if not timestamp:
            ts_match = TIMESTAMP_RE.search(segment_text[:500])
            if ts_match:
                timestamp = ts_match.group(0)

        parsed_ts = parse_timestamp_str(timestamp)

        seg = RequestSegment(
            id=stable_id(str(path), seg_index),
            source_file=str(path),
            project_name=project_name,
            segment_index=seg_index,
            raw_markdown=segment_text.strip(),
            preview=extract_preview(segment_text),
            timestamp=timestamp,
            parsed_timestamp=parsed_ts,
            conversation_id=conv_id,
            entry_number=entry_number,
            metrics=compute_metrics(segment_text),
        )
        conv_file.segments.append(seg)

    return conv_file


def scan_markdown_directory(markdown_dir: str) -> list:
    """Scan a directory of markdown files and return a list of Projects."""
    md_path = Path(markdown_dir)
    if not md_path.exists():
        return []

    md_files = sorted(md_path.glob("*.md"))

    # Group files into projects
    # Project name is derived from file name — the first 2 path segments
    # e.g. "IMPORTANT-Projects-oft-oft-frontend" -> project "IMPORTANT-Projects-oft"
    # But since each file IS a project, we treat each file as its own project
    projects_dict: dict[str, Project] = {}

    for md_file in md_files:
        # Project name = file stem
        name = md_file.stem
        # Create a more readable display name
        display = name.replace("-", " / ", 2).replace("-", " / ", 1) if "-" in name else name
        # Simpler: just use the stem
        display = name

        conv_file = parse_markdown_file(str(md_file), name)

        if name not in projects_dict:
            projects_dict[name] = Project(
                name=name,
                display_name=display,
            )

        projects_dict[name].files.append(conv_file)
        projects_dict[name].total_requests += len(conv_file.segments)

    return list(projects_dict.values())


def build_index(markdown_dir: str) -> dict:
    """Build the full index from a markdown directory.

    Returns a dict suitable for JSON serialization with:
    - projects: list of project summaries
    - segments: dict mapping segment_id -> full segment data
    """
    projects = scan_markdown_directory(markdown_dir)

    all_segments = {}
    project_summaries = []

    for project in projects:
        proj_segments = []
        for conv_file in project.files:
            for seg in conv_file.segments:
                tool_breakdown = compute_tool_breakdown(seg.raw_markdown)
                seg_data = {
                    "id": seg.id,
                    "source_file": seg.source_file,
                    "project_name": seg.project_name,
                    "segment_index": seg.segment_index,
                    "preview": seg.preview,
                    "timestamp": seg.timestamp,
                    "conversation_id": seg.conversation_id,
                    "entry_number": seg.entry_number,
                    "metrics": {
                        "char_count": seg.metrics.char_count,
                        "word_count": seg.metrics.word_count,
                        "line_count": seg.metrics.line_count,
                        "estimated_tokens": seg.metrics.estimated_tokens,
                        "tool_call_count": seg.metrics.tool_call_count,
                    },
                    "tool_breakdown": tool_breakdown,
                }
                proj_segments.append(seg_data)
                # Store full content separately
                all_segments[seg.id] = {
                    **seg_data,
                    "raw_markdown": seg.raw_markdown,
                }

        # Sort segments: by timestamp if available, else by segment_index
        proj_segments.sort(
            key=lambda s: (
                s["timestamp"] or "9999",
                s["segment_index"],
            )
        )

        project_summaries.append({
            "name": project.name,
            "display_name": project.display_name,
            "total_requests": project.total_requests,
            "total_files": len(project.files),
            "segment_ids": [s["id"] for s in proj_segments],
            "segments": proj_segments,
        })

    return {
        "projects": project_summaries,
        "segments": all_segments,
    }
