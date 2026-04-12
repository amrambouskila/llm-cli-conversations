"""Heuristic topic extraction for sessions.

Extracts 1-3 topics per session from:
1. Project name segments (split on '-')
2. File paths mentioned (extension -> language/tool keyword)
3. Keyword frequency in user messages (simple TF approach, top 3)
4. Tool-derived signals
"""

from __future__ import annotations

import re
from collections import Counter

# File extension -> topic keyword
EXTENSION_TOPICS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "react",
    ".jsx": "react",
    ".js": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".sql": "sql",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
    ".css": "css",
    ".html": "html",
    ".sh": "shell",
    ".bat": "shell",
    ".dockerfile": "docker",
}

# Keywords that map to specific topics when found in text
KEYWORD_TOPICS = {
    "docker": "docker",
    "dockerfile": "docker",
    "compose": "docker",
    "nginx": "nginx",
    "fastapi": "fastapi",
    "react": "react",
    "postgres": "database",
    "postgresql": "database",
    "sqlalchemy": "database",
    "redis": "redis",
    "git": "git",
    "ci/cd": "ci-cd",
    "gitlab": "ci-cd",
    "pipeline": "ci-cd",
    "deploy": "deployment",
    "kubernetes": "k8s",
    "k8s": "k8s",
    "test": "testing",
    "pytest": "testing",
    "vitest": "testing",
    "webpack": "bundling",
    "vite": "bundling",
    "api": "api",
    "websocket": "websocket",
    "auth": "authentication",
    "login": "authentication",
    "migration": "migration",
    "refactor": "refactoring",
    "debug": "debugging",
    "error": "debugging",
    "bug": "debugging",
    "css": "css",
    "style": "css",
    "chart": "visualization",
    "graph": "visualization",
    "plot": "visualization",
    "three.js": "3d",
    "threejs": "3d",
    "shader": "3d",
    "ml": "machine-learning",
    "model": "machine-learning",
    "embedding": "machine-learning",
    "search": "search",
}

# File path pattern
FILE_PATH_RE = re.compile(r"[\w/\\.-]+\.(\w{1,6})")

# Stopwords to exclude from keyword frequency
STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "about", "between",
    "through", "during", "before", "after", "above", "below", "up", "down",
    "out", "off", "over", "under", "again", "further", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no", "not",
    "only", "same", "so", "than", "too", "very", "just", "because", "but",
    "and", "or", "if", "while", "that", "this", "these", "those", "it",
    "its", "my", "your", "his", "her", "our", "their", "what", "which",
    "who", "whom", "me", "him", "us", "them", "i", "you", "he", "she",
    "we", "they", "file", "code", "make", "use", "add", "get", "set",
    "run", "let", "need", "want", "also", "like", "new", "now", "see",
    "try", "way", "change", "update", "create", "look", "sure", "right",
    "good", "don", "know", "think", "going", "still", "something",
})


def _project_name_topics(project_name: str) -> list[str]:
    """Extract topic candidates from project name segments."""
    parts = project_name.lower().replace("_", "-").split("-")
    # Filter out generic path segments
    skip = {"users", "important", "projects", "dev", "src", "app", "frontend", "backend"}
    return [p for p in parts if len(p) > 2 and p not in skip]


def _file_extension_topics(text: str) -> list[str]:
    """Extract topics from file extensions mentioned in text."""
    extensions = FILE_PATH_RE.findall(text.lower())
    topics = []
    for ext in extensions:
        dotted = f".{ext}"
        if dotted in EXTENSION_TOPICS:
            topics.append(EXTENSION_TOPICS[dotted])
    return topics


def _keyword_topics(text: str) -> list[str]:
    """Extract topics from keyword matches in text."""
    text_lower = text.lower()
    topics = []
    for keyword, topic in KEYWORD_TOPICS.items():
        if keyword in text_lower:
            topics.append(topic)
    return topics


def _frequency_topics(text: str, top_n: int = 3) -> list[tuple[str, int]]:
    """Extract top-N non-stopword terms by frequency."""
    words = re.findall(r"[a-z]{3,}", text.lower())
    filtered = [w for w in words if w not in STOPWORDS]
    return Counter(filtered).most_common(top_n)


def extract_topics(
    project_name: str,
    user_text: str,
    tool_names: list[str],
    max_topics: int = 5,
) -> list[tuple[str, float]]:
    """Extract topics for a session.

    Returns list of (topic, confidence) tuples, sorted by confidence desc.
    Confidence is a rough 0-1 score based on signal source.
    """
    scored: dict[str, float] = {}

    # Project name segments (high confidence — explicit context)
    for topic in _project_name_topics(project_name):
        scored[topic] = max(scored.get(topic, 0), 0.8)

    # File extension signals
    for topic in _file_extension_topics(user_text):
        scored[topic] = max(scored.get(topic, 0), 0.6)

    # Keyword matches
    for topic in _keyword_topics(user_text):
        scored[topic] = max(scored.get(topic, 0), 0.7)

    # Tool-derived signals
    tool_set = {t.lower() for t in tool_names}
    if "websearch" in tool_set or "webfetch" in tool_set:
        scored["research"] = max(scored.get("research", 0), 0.5)
    if "bash" in tool_set:
        scored["shell"] = max(scored.get("shell", 0), 0.3)

    # Frequency-based (lower confidence)
    for term, count in _frequency_topics(user_text):
        if term not in scored and count >= 3:
            scored[term] = 0.3

    # Sort by confidence, take top N
    ranked = sorted(scored.items(), key=lambda x: -x[1])
    return ranked[:max_topics]
