"""Heuristic session type classification.

Classifies each session into one of:
  coding, debugging, planning, research, writing, devops

Based on tool usage patterns, topic keywords, and session characteristics.
Logic from DESIGN.md §5.
"""

from __future__ import annotations

DEVOPS_KEYWORDS = frozenset({
    "docker", "ci", "deploy", "nginx", "k8s", "kubernetes", "pipeline",
    "compose", "dockerfile", "gitlab", "ci/cd", "helm", "terraform",
    "ansible", "infrastructure",
})


def classify_session(
    summary_text: str,
    tool_counts: dict[str, int],
    topics: list[str],
    total_words: int,
    turn_count: int,
) -> str:
    """Classify a session into a type based on heuristics.

    Returns one of: 'coding', 'debugging', 'planning', 'research',
    'writing', 'devops'.
    """
    topics_lower = {t.lower() for t in topics}
    summary_lower = (summary_text or "").lower()

    # DevOps: topic keywords match
    if topics_lower & DEVOPS_KEYWORDS:
        return "devops"

    edit_write_count = tool_counts.get("Edit", 0) + tool_counts.get("Write", 0)
    bash_count = tool_counts.get("Bash", 0)
    web_count = tool_counts.get("WebSearch", 0) + tool_counts.get("WebFetch", 0)
    total_tools = sum(tool_counts.values())

    # Coding: significant file editing
    if edit_write_count > 3:
        return "coding"

    # Debugging: lots of bash + error signals
    if bash_count > 5 and "error" in summary_lower:
        return "debugging"

    # Planning: low tool use, lots of words
    if total_tools < 3 and total_words > 2000:
        return "planning"

    # Research: web search usage
    if web_count > 0:
        return "research"

    # Research: short sessions with no edits
    if turn_count <= 4 and edit_write_count == 0:
        return "research"

    return "coding"
