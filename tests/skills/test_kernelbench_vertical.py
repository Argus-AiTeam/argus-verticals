"""Contract tests for the kernelbench vertical (from Argus's ``tests/skills/test_verticals.py``)."""
from __future__ import annotations

import json
from pathlib import Path

from argus_skill.skills.stage_machine import current_stage, format_full_pipeline_checklist
from argus_skill.skills.vertical_select import persist_vertical, require_vertical
from argus_skill.verticals._base import load_vertical
from argus_skill.verticals._registry import vertical_plugin


def _project(tmp_path: Path, vertical: str | None, *, current: str = "run") -> Path:
    (tmp_path / ".argus").mkdir(parents=True, exist_ok=True)
    payload: dict = {"current_stage": current}
    if vertical is not None:
        payload["vertical"] = vertical
    (tmp_path / ".argus" / "PIPELINE_STATE.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_require_vertical_accepts_installed_plugin_vertical() -> None:
    assert require_vertical("kernelbench") == "kernelbench"
    plugin = vertical_plugin("kernelbench")
    assert plugin is not None, "kernelbench is not registered with Argus's plugin registry"
    assert plugin.module.__name__ == "argus_verticals.kernelbench.stages"
    assert load_vertical("kernelbench") is plugin.module
    assert plugin.skill_parents == ("kernel_engineering",)


def test_kernelbench_keeps_research_as_valid_benchmark_research_stage(tmp_path: Path) -> None:
    root = _project(tmp_path, "kernelbench", current="research")

    persist_vertical(root, "kernelbench")

    payload = json.loads((root / ".argus" / "PIPELINE_STATE.json").read_text())
    assert payload["vertical"] == "kernelbench"
    assert payload["current_stage"] == "research"
    assert current_stage(root) == "research"


def test_kernelbench_research_checklist_is_not_paper_literature_gate(tmp_path: Path) -> None:
    root = _project(tmp_path, "kernelbench", current="research")

    text = format_full_pipeline_checklist(role="reviewer", project_root=root)

    assert "### research" in text
    assert "SOTA-oriented technique research" in text
    assert "research.first_score_plan" in text
    assert "at least 10 recent high-quality papers" not in text


def test_kernelbench_stage_completion_requires_scored_kernel_and_report(tmp_path: Path) -> None:
    from argus_verticals.kernelbench.stages import stage_completion_issues

    assert "correct=true" in " ".join(stage_completion_issues("measure", tmp_path))

    result = tmp_path / "attempts" / "a1" / "result.csv"
    result.parent.mkdir(parents=True)
    result.write_text("correct,sol_pct\ntrue,72.5\n", encoding="utf-8")
    assert stage_completion_issues("measure", tmp_path) == ()

    assert stage_completion_issues("report", tmp_path)
    (tmp_path / "RESULTS.md").write_text("# Results\n", encoding="utf-8")
    assert stage_completion_issues("report", tmp_path) == ()
