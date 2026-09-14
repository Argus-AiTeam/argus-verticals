"""Contract tests for the speedrun vertical.

The stage-completion and banner cases come from Argus's ``tests/skills/test_verticals.py``
(moved with the vertical); the Manager kind and live-search cases from
``tests/skills/test_argus_maintenance_vertical.py`` and ``tests/test_codex_live_search.py``.
"""
from __future__ import annotations

from pathlib import Path

from argus.manager import Manager
from argus.verticals._base import load_vertical, load_vertical_contract
from argus.verticals._registry import vertical_plugin
from argus.verticals.optimization_base import (
    OPTIMIZATION_CHECKLIST_ITEMS,
    OPTIMIZATION_STAGE_ORDER,
)

from argus_verticals.speedrun import stages
from argus_verticals.speedrun.stages import role_banner as speedrun_role_banner


def test_speedrun_is_registered_and_loadable() -> None:
    plugin = vertical_plugin("speedrun")
    assert plugin is not None, "speedrun is not registered with Argus's plugin registry"
    assert plugin.module.__name__ == "argus_verticals.speedrun.stages"
    assert load_vertical("speedrun") is plugin.module
    assert Manager._kind_for("speedrun") == "optimize"


def test_speedrun_reuses_the_framework_optimization_checklist() -> None:
    """The four-stage metric checklist is owned by Argus's bridge; speedrun
    specialises it rather than carrying a copy that could drift."""
    assert stages.CHECKLIST_STAGE_ORDER == OPTIMIZATION_STAGE_ORDER
    assert tuple(stages.STAGE_ORDER) == OPTIMIZATION_STAGE_ORDER
    assert stages.CHECKLIST_ITEMS == OPTIMIZATION_CHECKLIST_ITEMS
    assert stages.CHECKLIST_ITEMS is not OPTIMIZATION_CHECKLIST_ITEMS
    for stage, items in stages.CHECKLIST_ITEMS.items():
        assert items is OPTIMIZATION_CHECKLIST_ITEMS[stage]


def test_speedrun_stage_completion_requires_scored_run_and_report(tmp_path: Path) -> None:
    from argus_verticals.speedrun.stages import stage_completion_issues

    assert "results.csv" in " ".join(stage_completion_issues("measure", tmp_path))

    result = tmp_path / "attempts" / "a1" / "results.csv"
    result.parent.mkdir(parents=True)
    result.write_text("score\n0.5\n", encoding="utf-8")
    assert stage_completion_issues("measure", tmp_path) == ()

    assert stage_completion_issues("report", tmp_path)
    (tmp_path / "RESULTS.md").write_text("# Results\n", encoding="utf-8")
    assert stage_completion_issues("report", tmp_path) == ()


def test_speedrun_reviewer_banner_is_innovation_coach() -> None:
    banner = speedrun_role_banner("reviewer")
    assert "INNOVATION COACH" in banner


def test_speedrun_without_a_live_search_declaration_takes_the_default_path() -> None:
    from argus.engineer.round_config import DEFAULT_LIVE_SEARCH_STAGES

    contract = load_vertical_contract("speedrun")
    assert contract.engineer_live_search_stages is None
    assert contract.live_search_stages(DEFAULT_LIVE_SEARCH_STAGES) == frozenset(contract.stage_order)
