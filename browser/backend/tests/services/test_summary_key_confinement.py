"""Summary keys come from URL path params; every filesystem access must stay inside SUMMARIES_DIR."""
from __future__ import annotations

import pytest

from services import summary_service as sm
from services.summary_service import InvalidSummaryKeyError, SummaryService


@pytest.fixture(autouse=True)
def _point_summary_dir_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(sm, "SUMMARIES_DIR", tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    "key",
    ["seg-1a", "0123456789abcdef", "conv_IMPORTANT-Projects_0f6c2e3a-1b2c", "conv_x_y__r0_3"],
)
def test_well_formed_keys_resolve_inside_store(key, tmp_path):
    target = sm._summary_file(key, ".md")
    assert target.parent == tmp_path.resolve()
    assert target.name == f"{key}.md"


@pytest.mark.parametrize(
    "key",
    ["../etc/passwd", "..", ".", "a/b", "a\\b", ".hidden", "", "key.md", "con v", "‮"],
)
def test_malformed_keys_are_rejected_before_any_filesystem_access(key):
    with pytest.raises(InvalidSummaryKeyError):
        sm._summary_file(key, ".md")


def test_service_entry_points_reject_traversal(db_session, tmp_path):
    svc = SummaryService(db_session)
    with pytest.raises(InvalidSummaryKeyError):
        svc.get_segment_summary("../../outside")
    with pytest.raises(InvalidSummaryKeyError):
        svc.delete_summary("../../outside")
    assert not (tmp_path.parent / "outside.md").exists()


def test_link_planted_in_the_store_cannot_smuggle_a_key_outside_it(tmp_path, tmp_path_factory):
    """The regex admits ``escape``; only the resolve() guard catches a link pointing out of the store."""
    outside = tmp_path_factory.mktemp("outside_store")
    link = tmp_path / "escape.md"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        # Windows refuses symlinks without Developer Mode or admin (WinError 1314); a directory
        # junction needs no privilege and Path.resolve() follows it identically.
        import _winapi

        _winapi.CreateJunction(str(outside), str(link))

    assert link.resolve() == outside.resolve()

    with pytest.raises(InvalidSummaryKeyError, match="escapes the summary store"):
        sm._summary_file("escape", ".md")
