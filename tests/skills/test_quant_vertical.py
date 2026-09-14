"""Contract and skill-seeding tests for the quant vertical.

The contract cases come from Argus's ``tests/skills/test_verticals.py``, the
seeding cases from ``tests/skills/test_builtins_seeding.py`` (both moved with the
vertical). ``quant`` is the finance analog of ``research``: a REPORT vertical (it
produces a reviewer-certified factor report, not a numeric metric), reusing the
same 8 stage ids with finance semantics. Its skills are served through
``VERTICAL_SKILLS`` on the plugin module and seeded by Argus's real seeder.
"""
from __future__ import annotations

import json
from pathlib import Path

from argus_skill.manager import Manager
from argus_skill.skills.builtins import (
    iter_vertical_skill_texts,
    seed_builtin_skills_for_vertical,
)
from argus_skill.skills.stage_machine import format_full_pipeline_checklist
from argus_skill.verticals._base import load_vertical, vertical_completion_gate
from argus_skill.verticals._registry import vertical_plugin

QUANT_STAGES: tuple[str, ...] = (
    "research", "plan", "benchmark", "run",
    "analysis", "draft", "review", "submission",
)
QUANT_SKILLS = {
    "engineer/quant-factor-loop.md",
    "engineer/model-selection-loop.md",
    "engineer/kline-chart.md",
    "reviewer/quant-factor-report-review.md",
}


def _project(tmp_path: Path, vertical: str | None, *, current: str = "run") -> Path:
    (tmp_path / ".argus").mkdir(parents=True, exist_ok=True)
    payload: dict = {"current_stage": current}
    if vertical is not None:
        payload["vertical"] = vertical
    (tmp_path / ".argus" / "PIPELINE_STATE.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


# --- contract ---------------------------------------------------------------


def test_quant_vertical_loads_and_exposes_contract() -> None:
    plugin = vertical_plugin("quant")
    assert plugin is not None, "quant is not registered with Argus's plugin registry"
    assert plugin.module.__name__ == "argus_verticals.quant.stages"
    mod = load_vertical("quant")
    assert mod is plugin.module
    assert tuple(mod.STAGE_ORDER) == QUANT_STAGES
    assert vertical_completion_gate(mod) == "certified"


def test_quant_is_a_report_vertical_not_optimize() -> None:
    assert Manager._kind_for("quant") == "research"


def test_quant_full_pipeline_checklist_is_finance_not_paper(tmp_path: Path) -> None:
    root = _project(tmp_path, "quant", current="run")

    text = format_full_pipeline_checklist(role="reviewer", project_root=root)

    for stage in QUANT_STAGES:
        assert f"### {stage}\n" in text
    assert "research.hypotheses" in text
    assert "research.hypothesis_priors" in text
    assert "economic" in text
    assert "search ledger" in text
    assert "final submission gate" in text


# --- skill seeding through Argus's real seeder --------------------------------


def test_iter_vertical_skill_texts_quant() -> None:
    got = {name for name, _ in iter_vertical_skill_texts("quant")}
    assert got == QUANT_SKILLS


def test_quant_skills_are_owned_by_the_quant_vertical(tmp_path) -> None:
    seed_builtin_skills_for_vertical(tmp_path, "quant", overwrite=True)
    for rel in QUANT_SKILLS:
        body = (tmp_path / rel).read_text(encoding="utf-8")
        assert "MOVED" not in body, f"pointer stub leaked into workspace for {rel}"


def test_seed_for_vertical_overwrites_stub_with_real_body(tmp_path) -> None:
    seed_builtin_skills_for_vertical(tmp_path, "quant", overwrite=True)
    for rel in QUANT_SKILLS:
        body = (tmp_path / rel).read_text(encoding="utf-8")
        assert "MOVED" not in body, f"stub leaked into workspace for {rel}"
    assert "strict quant-research referee" in (
        tmp_path / "reviewer" / "quant-factor-report-review.md"
    ).read_text(encoding="utf-8")
    assert "BacktestExecutor" in (
        tmp_path / "engineer" / "quant-factor-loop.md"
    ).read_text(encoding="utf-8")


def test_seed_for_vertical_preserves_operator_edit_without_overwrite(tmp_path) -> None:
    path = tmp_path / "engineer" / "quant-factor-loop.md"
    path.parent.mkdir(parents=True)
    path.write_text("operator-owned quant workflow\n", encoding="utf-8")

    changed = seed_builtin_skills_for_vertical(tmp_path, "quant")

    assert changed["engineer/quant-factor-loop.md"] is False
    assert path.read_text(encoding="utf-8") == "operator-owned quant workflow\n"


def test_seed_for_vertical_keeps_general_skills_without_research_leakage(tmp_path) -> None:
    seed_builtin_skills_for_vertical(tmp_path, "quant", overwrite=True)
    assert (tmp_path / "engineer" / "argus-engineer-role.md").exists()
    assert not (tmp_path / "reviewer" / "experiment-plan-review.md").exists()


def test_seed_for_research_does_not_pull_quant_real_body(tmp_path) -> None:
    seed_builtin_skills_for_vertical(tmp_path, "research", overwrite=True)
    for relative in QUANT_SKILLS:
        assert not (tmp_path / relative).exists(), relative
