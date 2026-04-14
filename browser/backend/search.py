from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel


class SearchFilters(BaseModel):
    project: str | None = None
    model: str | None = None
    provider: str | None = None
    after: date | None = None
    before: date | None = None
    tools: list[str] | None = None
    topic: str | None = None
    min_cost: float | None = None
    min_turns: int | None = None


class ParsedQuery(BaseModel):
    text: str
    filters: SearchFilters


# Patterns for structured filter prefixes.
# Each tuple: (regex pattern, filter field name, value parser)
_FILTER_PATTERNS: list[tuple[re.Pattern, str, callable]] = [
    (re.compile(r"project:(\S+)", re.IGNORECASE), "project", str),
    (re.compile(r"model:(\S+)", re.IGNORECASE), "model", str),
    (re.compile(r"provider:(\S+)", re.IGNORECASE), "provider", str),
    (re.compile(r"after:(\S+)", re.IGNORECASE), "after", lambda v: date.fromisoformat(v)),
    (re.compile(r"before:(\S+)", re.IGNORECASE), "before", lambda v: date.fromisoformat(v)),
    (re.compile(r"tool:(\S+)", re.IGNORECASE), "tools", lambda v: [t for t in v.split(",") if t]),
    (re.compile(r"topic:(\S+)", re.IGNORECASE), "topic", str),
    (re.compile(r"cost:>(\S+)", re.IGNORECASE), "min_cost", float),
    (re.compile(r"turns:>(\S+)", re.IGNORECASE), "min_turns", int),
]


def parse_query(raw: str) -> ParsedQuery:
    """Parse a search string with optional structured filter prefixes.

    Example: "project:conversations after:2026-03-01 tool:Bash docker auth"
    Returns: ParsedQuery(text="docker auth", filters=SearchFilters(project="conversations", ...))
    """
    text = raw.strip()
    filter_values: dict[str, object] = {}

    for pattern, field, parser in _FILTER_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                filter_values[field] = parser(match.group(1))
            except (ValueError, TypeError):
                # Malformed filter value — leave it in the text as-is
                continue
            text = text[:match.start()] + text[match.end():]

    # Collapse whitespace left by extracted tokens
    text = " ".join(text.split())

    return ParsedQuery(
        text=text,
        filters=SearchFilters(**filter_values),
    )