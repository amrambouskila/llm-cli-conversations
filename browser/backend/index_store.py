"""Global in-memory index storage.

Extracted from app.py to avoid circular imports between app.py and route
modules. app.py writes to these globals (on startup and rebuild); route
modules only read via get_index().
"""

from parser import build_index

INDEX: dict = {}
CODEX_INDEX: dict = {}
INDEXES: dict = {}


def init_indexes(markdown_dir: str, codex_markdown_dir: str) -> None:
    """Build indexes from markdown directories. Called once at startup."""
    global INDEX, CODEX_INDEX, INDEXES

    print(f"Indexing Claude markdown from: {markdown_dir}")
    INDEX = build_index(markdown_dir)
    print(f"Claude: {len(INDEX['projects'])} projects, {len(INDEX['segments'])} segments")

    print(f"Indexing Codex markdown from: {codex_markdown_dir}")
    CODEX_INDEX = build_index(codex_markdown_dir)
    print(f"Codex: {len(CODEX_INDEX['projects'])} projects, {len(CODEX_INDEX['segments'])} segments")

    INDEXES = {"claude": INDEX, "codex": CODEX_INDEX}


def rebuild_index(provider: str, markdown_dir: str) -> dict:
    """Rebuild a single provider's index and update the global store."""
    global INDEX, CODEX_INDEX
    new_index = build_index(markdown_dir)
    if provider == "claude":
        INDEX = new_index
    elif provider == "codex":
        CODEX_INDEX = new_index
    INDEXES[provider] = new_index
    return new_index


def get_index(provider: str = "claude") -> dict:
    """Get the index for the given provider."""
    return INDEXES.get(provider, INDEX)
