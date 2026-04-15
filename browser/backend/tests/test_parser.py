"""Unit tests for parser.py edge cases.

Covers the uncovered branches in parser.py:
- extract_preview() delimiter/comment/heading skip branches + long-line truncation + empty-request fallback
- parse_timestamp_str() None input + fallback format parsing
- parse_markdown_file() no-user-request whole-file path
- parse_markdown_file() conv-marker-within-segment update
- parse_markdown_file() timestamp fallback from segment text when heading lacks timestamp
- scan_markdown_directory() non-existent directory
"""
from __future__ import annotations

from datetime import datetime

from parser import (
    extract_preview,
    parse_markdown_file,
    parse_timestamp_str,
    scan_markdown_directory,
)

# ---------------------------------------------------------------------------
# extract_preview
# ---------------------------------------------------------------------------

def test_extract_preview_skips_triple_angle_delimiter():
    """Lines starting with >>> are delimiters, not content."""
    text = ">>>USER_REQUEST<<<\nreal content here"
    assert extract_preview(text) == "real content here"


def test_extract_preview_skips_html_comment():
    """<!-- ENTRY_KEY: ... --> lines are skipped."""
    text = "<!-- ENTRY_KEY: abc123 -->\nreal content here"
    assert extract_preview(text) == "real content here"


def test_extract_preview_skips_heading_line():
    """Lines starting with # are headings."""
    text = "# User #1 — 2026-03-15 — conv: `c`\nreal content here"
    assert extract_preview(text) == "real content here"


def test_extract_preview_truncates_at_max_len():
    """Long content lines are cut at max_len + '...'"""
    long_line = "x" * 200
    result = extract_preview(long_line, max_len=50)
    assert result == ("x" * 50) + "..."


def test_extract_preview_empty_text_returns_sentinel():
    """When nothing matches, fallback is '(empty request)'."""
    assert extract_preview("") == "(empty request)"
    assert extract_preview("\n\n\n") == "(empty request)"
    assert extract_preview(">>>only delim<<<") == "(empty request)"


# ---------------------------------------------------------------------------
# parse_timestamp_str
# ---------------------------------------------------------------------------

def test_parse_timestamp_str_none_returns_none():
    assert parse_timestamp_str(None) is None


def test_parse_timestamp_str_empty_returns_none():
    assert parse_timestamp_str("") is None


def test_parse_timestamp_str_unrecognized_format_returns_none():
    """After all 4 format attempts fail → returns None."""
    assert parse_timestamp_str("not-a-real-timestamp") is None
    assert parse_timestamp_str("2026/03/15") is None


def test_parse_timestamp_str_iso_with_microseconds_and_z():
    result = parse_timestamp_str("2026-03-15T12:00:00.123456Z")
    assert isinstance(result, datetime)
    assert result.year == 2026


def test_parse_timestamp_str_iso_without_microseconds_with_z():
    result = parse_timestamp_str("2026-03-15T12:00:00Z")
    assert isinstance(result, datetime)
    assert result.hour == 12


def test_parse_timestamp_str_iso_with_microseconds_no_z():
    result = parse_timestamp_str("2026-03-15T12:00:00.123456")
    assert isinstance(result, datetime)


def test_parse_timestamp_str_iso_no_microseconds_no_z():
    """Triggers the final for-loop branch (4th format attempt)."""
    result = parse_timestamp_str("2026-03-15T12:00:00")
    assert isinstance(result, datetime)


# ---------------------------------------------------------------------------
# parse_markdown_file — no-user-request whole-file path
# ---------------------------------------------------------------------------

def test_parse_markdown_file_without_user_request_delim(tmp_path):
    """File lacking >>>USER_REQUEST<<< becomes one segment."""
    path = tmp_path / "plain.md"
    path.write_text(
        "# some project\n\nJust plain markdown\nwith no delimiters.\n",
        encoding="utf-8",
    )
    conv = parse_markdown_file(str(path), "some_project")
    assert len(conv.segments) == 1
    assert "Just plain markdown" in conv.segments[0].raw_markdown
    assert conv.segments[0].segment_index == 0


# ---------------------------------------------------------------------------
# parse_markdown_file — conv marker within segment + timestamp text fallback
# ---------------------------------------------------------------------------

def test_parse_markdown_file_conv_marker_in_segment(tmp_path):
    """A `## Conversation` marker inside a segment updates `current_conv_id` for FOLLOWING segments.

    (The segment whose body contains the marker retains the `conv_id` set by its own heading.
    Subsequent segments whose heading omits `conv: \\`uuid\\`` fall back to current_conv_id.)
    """
    md = (
        "# proj\n\n"
        "## Conversation `conv-A` (started 2026-03-15T12:00:00.000Z)\n\n"
        ">>>USER_REQUEST<<<\n"
        "# User #1 \u2014 2026-03-15T12:00:00.000Z \u2014 conv: `conv-A`\n\n"
        "first request\n\n"
        ">>>USER_REQUEST<<<\n"
        "# User #2 \u2014 2026-03-15T13:00:00.000Z\n\n"
        "## Conversation `conv-B` (started 2026-03-15T14:00:00.000Z)\n\n"
        "second request body containing a new conversation marker\n\n"
        ">>>USER_REQUEST<<<\n"
        "# User #3 \u2014 2026-03-15T15:00:00.000Z\n\n"
        "third request inherits current_conv_id set by the in-segment marker\n"
    )
    path = tmp_path / "conv_switch.md"
    path.write_text(md, encoding="utf-8")
    conv = parse_markdown_file(str(path), "proj")
    assert len(conv.segments) == 3
    assert conv.segments[0].conversation_id == "conv-A"
    # Segment #3 inherits conv-B via the current_conv_id update that happened during seg #2.
    assert conv.segments[2].conversation_id == "conv-B"


def test_parse_markdown_file_timestamp_fallback_from_body(tmp_path):
    """When the heading omits the timestamp, a fallback scan of the first 500 chars grabs it."""
    md = (
        "# proj\n\n"
        ">>>USER_REQUEST<<<\n"
        "# User #1\n\n"  # no timestamp in the heading
        "Some text with a timestamp 2026-03-15T12:00:00.000Z elsewhere.\n"
    )
    path = tmp_path / "ts_fallback.md"
    path.write_text(md, encoding="utf-8")
    conv = parse_markdown_file(str(path), "proj")
    assert conv.segments[0].timestamp == "2026-03-15T12:00:00.000Z"


# ---------------------------------------------------------------------------
# scan_markdown_directory
# ---------------------------------------------------------------------------

def test_scan_markdown_directory_nonexistent_returns_empty(tmp_path):
    assert scan_markdown_directory(str(tmp_path / "does-not-exist")) == []
