"""Unit tests for topics.extract_topics — every signal source."""
from __future__ import annotations

import pytest

from topics import (
    EXTENSION_TOPICS,
    KEYWORD_TOPICS,
    _file_extension_topics,
    _frequency_topics,
    _keyword_topics,
    _project_name_topics,
    extract_topics,
)

# ---------------------------------------------------------------------------
# _project_name_topics
# ---------------------------------------------------------------------------

def test_project_name_splits_on_dash():
    out = _project_name_topics("conversations-browser")
    assert "conversations" in out
    assert "browser" in out


def test_project_name_underscore_normalised_to_dash():
    out = _project_name_topics("data_pipeline_v2")
    assert "data" in out
    assert "pipeline" in out


def test_project_name_skips_generic_segments():
    out = _project_name_topics("users-important-projects-real-app")
    assert "users" not in out
    assert "important" not in out
    assert "projects" not in out
    assert "app" not in out
    assert "real" in out


def test_project_name_skips_short_segments():
    out = _project_name_topics("ai-ml-data")
    # "ai" and "ml" are length 2, dropped; "data" survives
    assert "ai" not in out
    assert "ml" not in out
    assert "data" in out


def test_project_name_lowercased():
    out = _project_name_topics("MixedCase-Project")
    assert all(t == t.lower() for t in out)


# ---------------------------------------------------------------------------
# _file_extension_topics
# ---------------------------------------------------------------------------

def test_file_extension_python():
    assert "python" in _file_extension_topics("see src/foo.py for details")


def test_file_extension_typescript():
    assert "typescript" in _file_extension_topics("edit handler.ts")


def test_file_extension_react_tsx():
    assert "react" in _file_extension_topics("update App.tsx")


def test_file_extension_unknown_extension_ignored():
    out = _file_extension_topics("see file.xyz")
    assert out == []


def test_file_extension_no_paths_returns_empty():
    assert _file_extension_topics("just plain words") == []


# FILE_PATH_RE captures at most 6 chars after the dot; entries with longer
# extensions can't reach the lookup. Currently only .dockerfile (10 chars).
_REGEX_REACHABLE = [(e, t) for e, t in EXTENSION_TOPICS.items() if len(e) - 1 <= 6]


@pytest.mark.parametrize("ext, topic", _REGEX_REACHABLE)
def test_every_extension_resolves_to_its_topic(ext, topic):
    out = _file_extension_topics(f"file/path{ext}")
    assert topic in out


def test_dockerfile_extension_unreachable_by_regex():
    """`.dockerfile` is in EXTENSION_TOPICS but FILE_PATH_RE caps at 6 chars
    after the dot, so this entry is dead. Captured here so Phase 7 makes an
    explicit decision (widen regex or drop the entry)."""
    out = _file_extension_topics("a/path.dockerfile")
    assert "docker" not in out


# ---------------------------------------------------------------------------
# _keyword_topics
# ---------------------------------------------------------------------------

def test_keyword_match_docker():
    assert "docker" in _keyword_topics("we discussed docker setup")


def test_keyword_case_insensitive():
    assert "docker" in _keyword_topics("DOCKER compose")


def test_keyword_no_match_returns_empty():
    assert _keyword_topics("the quick brown fox") == []


@pytest.mark.parametrize("keyword, topic", list(KEYWORD_TOPICS.items()))
def test_every_keyword_resolves_to_its_topic(keyword, topic):
    assert topic in _keyword_topics(f"some context {keyword} more context")


# ---------------------------------------------------------------------------
# _frequency_topics
# ---------------------------------------------------------------------------

def test_frequency_drops_stopwords():
    text = "the the the the the the cat dog dog dog"
    counts = dict(_frequency_topics(text, top_n=5))
    assert "the" not in counts
    assert counts.get("dog") == 3
    assert counts.get("cat") == 1


def test_frequency_drops_short_words():
    text = "ab ab ab cat cat cat"
    counts = dict(_frequency_topics(text))
    # 2-char "ab" excluded by the [a-z]{3,} regex
    assert "ab" not in counts
    assert "cat" in counts


def test_frequency_top_n_limits_results():
    text = "alpha beta gamma delta epsilon zeta eta theta"
    out = _frequency_topics(text, top_n=3)
    assert len(out) == 3


# ---------------------------------------------------------------------------
# extract_topics — combined behaviour
# ---------------------------------------------------------------------------

def test_extract_topics_returns_sorted_by_confidence_desc():
    out = extract_topics(
        project_name="myproject",
        user_text="docker docker docker frequent frequent frequent",
        tool_names=[],
    )
    confidences = [c for _, c in out]
    assert confidences == sorted(confidences, reverse=True)


def test_project_name_signal_high_confidence():
    out = dict(extract_topics("conversations", "", []))
    assert out.get("conversations") == 0.8


def test_keyword_signal_confidence():
    out = dict(extract_topics("xx", "we are using docker today", []))
    assert out.get("docker") == 0.7


def test_file_extension_signal_confidence():
    out = dict(extract_topics("xx", "edit src/foo.py", []))
    assert out.get("python") == 0.6


def test_keyword_overrides_file_extension_when_higher():
    # docker keyword (0.7) wins over a hypothetical lower signal
    out = dict(extract_topics("xx", "docker compose up", []))
    assert out["docker"] == 0.7


def test_websearch_tool_signal():
    out = dict(extract_topics("xx", "", ["WebSearch"]))
    assert out.get("research") == 0.5


def test_webfetch_tool_signal():
    out = dict(extract_topics("xx", "", ["WebFetch"]))
    assert out.get("research") == 0.5


def test_bash_tool_signal():
    out = dict(extract_topics("xx", "", ["Bash"]))
    assert out.get("shell") == 0.3


def test_tool_names_lowercased_for_matching():
    out = dict(extract_topics("xx", "", ["BASH"]))
    assert out.get("shell") == 0.3


def test_frequency_only_added_when_term_not_already_scored():
    # "docker" already scored from keywords; the frequency pass should not
    # downgrade it back to 0.3
    out = dict(extract_topics("xx", "docker docker docker", []))
    assert out["docker"] == 0.7


def test_frequency_requires_count_at_least_three():
    # "frequent" appears twice — below the count >= 3 threshold
    out = dict(extract_topics("xx", "frequent frequent unrelated other words", []))
    assert "frequent" not in out


def test_frequency_added_when_count_three_or_more():
    out = dict(extract_topics(
        project_name="xx",
        user_text="newword newword newword something else here",
        tool_names=[],
    ))
    assert out.get("newword") == 0.3


def test_max_topics_cap_applied():
    # Generate many distinct project segments and keyword hits to overflow 5
    text = "docker postgres redis fastapi react"
    out = extract_topics("alpha-beta-gamma-delta-epsilon", text, [])
    assert len(out) <= 5


def test_max_topics_custom_value():
    out = extract_topics(
        project_name="alpha-beta-gamma-delta-epsilon",
        user_text="docker postgres redis",
        tool_names=[],
        max_topics=2,
    )
    assert len(out) == 2


def test_no_signals_returns_empty():
    assert extract_topics("", "", []) == []


def test_returns_list_of_tuples():
    out = extract_topics("xx", "docker", [])
    assert all(isinstance(item, tuple) and len(item) == 2 for item in out)
