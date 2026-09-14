"""Paper-mission and final-certification classification of the verticals here.

From Argus's ``tests/test_vertical_paper_mission.py``: quant and medical use
``certified`` completion but must not inherit the research paper pipeline; the
optimize verticals are never paper missions.
"""
from __future__ import annotations

import pytest
from argus_skill.apps._runtime import (
    _final_certification_for_project_root,
    _paper_mission_for_project_root,
)
from argus_skill.skills.vertical_select import persist_vertical
from argus_skill.verticals._base import load_vertical, vertical_is_paper_mission


@pytest.mark.parametrize("vertical", ["kernelbench", "speedrun", "nanochat", "nanogpt_speedrun"])
def test_optimize_verticals_are_not_paper(vertical: str) -> None:
    assert vertical_is_paper_mission(load_vertical(vertical)) is False


@pytest.mark.parametrize("vertical", ["medical", "quant"])
def test_certified_nonpaper_verticals_are_not_paper(vertical: str) -> None:
    assert vertical_is_paper_mission(load_vertical(vertical)) is False


@pytest.mark.parametrize("vertical", ["medical", "quant"])
def test_certified_verticals_keep_final_certification(tmp_path, vertical: str) -> None:
    persist_vertical(tmp_path, vertical)
    assert _final_certification_for_project_root(tmp_path) is True


def test_persisted_bounded_vertical_is_not_paper(tmp_path) -> None:
    persist_vertical(tmp_path, "kernelbench")
    assert _paper_mission_for_project_root(tmp_path) is False
