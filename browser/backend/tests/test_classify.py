"""Unit tests for classify.classify_session — every branch in the decision chain."""
from __future__ import annotations

import pytest

from classify import DEVOPS_KEYWORDS, classify_session


@pytest.mark.parametrize("topic", sorted(DEVOPS_KEYWORDS))
def test_devops_topic_wins(topic):
    assert classify_session("", {}, [topic], total_words=0, turn_count=0) == "devops"


def test_devops_topic_case_insensitive():
    assert classify_session("", {}, ["DOCKER"], total_words=0, turn_count=0) == "devops"


def test_coding_when_edit_plus_write_exceeds_three():
    counts = {"Edit": 2, "Write": 2}
    assert classify_session("anything", counts, [], total_words=0, turn_count=0) == "coding"


def test_coding_threshold_is_strictly_greater_than_three():
    # Edit+Write == 3 should NOT trigger coding
    counts = {"Edit": 2, "Write": 1}
    # With these inputs no other branch matches either; falls through to default "coding"
    assert classify_session("", counts, [], total_words=0, turn_count=10) == "coding"


def test_debugging_requires_bash_gt_5_and_error_in_summary():
    counts = {"Bash": 6}
    assert classify_session("hit an error here", counts, [], total_words=0, turn_count=20) == "debugging"


def test_debugging_not_triggered_without_error_keyword():
    counts = {"Bash": 6}
    # No "error" word in summary, no other matching branch — falls to default coding
    assert classify_session("all good", counts, [], total_words=0, turn_count=20) == "coding"


def test_debugging_not_triggered_when_bash_below_six():
    counts = {"Bash": 5}
    # Without devops, edit+write, or web → matches turn_count<=4 branch? turn_count=20 → no
    # → default coding
    assert classify_session("we hit an error", counts, [], total_words=0, turn_count=20) == "coding"


def test_planning_low_tools_high_words():
    counts = {"Read": 2}
    assert classify_session("plan", counts, [], total_words=2500, turn_count=4) == "planning"


def test_planning_requires_total_words_strictly_greater_than_2000():
    counts = {"Read": 1}
    # 2000 == 2000, not > 2000 — should NOT be planning. With turn_count=4 and no edit, hits
    # the research branch.
    assert classify_session("p", counts, [], total_words=2000, turn_count=4) == "research"


def test_research_via_websearch():
    counts = {"WebSearch": 1}
    assert classify_session("", counts, [], total_words=0, turn_count=10) == "research"


def test_research_via_webfetch():
    counts = {"WebFetch": 1}
    assert classify_session("", counts, [], total_words=0, turn_count=10) == "research"


def test_research_short_session_no_edits():
    counts = {"Read": 1}
    assert classify_session("", counts, [], total_words=100, turn_count=3) == "research"


def test_research_short_session_boundary_turn_count_four():
    counts = {"Read": 1}
    assert classify_session("", counts, [], total_words=100, turn_count=4) == "research"


def test_research_short_session_blocked_when_edits_present():
    counts = {"Edit": 1, "Read": 1}
    # turn_count <= 4 and Edit==1 → edit_write_count != 0 → does not match research branch
    # falls to default coding
    assert classify_session("", counts, [], total_words=100, turn_count=4) == "coding"


def test_default_coding_when_no_signals_match():
    assert classify_session("", {}, [], total_words=0, turn_count=10) == "coding"


def test_devops_takes_precedence_over_coding():
    # Lots of edits, but topic is devops — devops wins
    counts = {"Edit": 5, "Write": 5}
    assert classify_session("", counts, ["docker"], total_words=0, turn_count=0) == "devops"


def test_coding_takes_precedence_over_debugging():
    # Many edits AND lots of bash with error — coding wins (it's earlier in the chain)
    counts = {"Edit": 4, "Bash": 10}
    assert classify_session("error happened", counts, [], total_words=0, turn_count=0) == "coding"


def test_coding_takes_precedence_over_planning():
    counts = {"Edit": 4}
    assert classify_session("", counts, [], total_words=5000, turn_count=4) == "coding"


def test_summary_text_lowercased_for_error_check():
    counts = {"Bash": 6}
    assert classify_session("ERROR happened", counts, [], total_words=0, turn_count=20) == "debugging"


def test_summary_none_treated_as_empty():
    counts = {"Bash": 6}
    # None summary → falls to default coding (no error keyword found)
    assert classify_session(None, counts, [], total_words=0, turn_count=20) == "coding"


def test_topics_lowercased_for_devops_match():
    assert classify_session("", {}, ["Docker"], total_words=0, turn_count=0) == "devops"
