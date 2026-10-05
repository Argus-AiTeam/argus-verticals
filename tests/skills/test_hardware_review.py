from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from argus.core.pipeline_state import read_pipeline_state, write_pipeline_state
from argus.engineer.round_evidence import RoundEvidenceRequest, collect_round_evidence
from argus.roles.prompts import ChecklistMode, RoleName, RolePromptRequest, resolve_role_prompt
from argus.skills.vertical_select import persist_vertical

from argus_verticals.hardware.shared.review import round_evidence, verification_review_contract

SPECIALISTS = [
    ("analog_mixed_signal", "simulation"), ("rf_design", "analysis"),
    ("pcb_design", "verification"), ("package_design", "thermal"),
    ("power_electronics", "simulation"),
]


@pytest.mark.parametrize("vertical,stage", [
    ("chip_design", "verification"),
    ("digital_circuit", "verification"),
    ("digital_circuit_verification", "plan"),
    ("digital_circuit_verification", "simulation"),
    ("digital_circuit_verification", "formal"),
    ("digital_circuit_verification", "review"),
    *[("fpga_design", stage) for stage in
      ("requirements", "rtl", "verification", "implementation", "bringup", "delivery")],
    *[(vertical, stage) for vertical, execution in SPECIALISTS
      for stage in ("specification", "design" if vertical == "pcb_design" else "model", execution, "review")],
])
def test_host_uses_saved_scope_and_execution_root_without_writing(tmp_path, monkeypatch, vertical, stage):
    module = "digital_circuit.verification" if vertical == "digital_circuit_verification" else vertical
    stages = importlib.import_module(f"argus_verticals.{module}.stages")
    calls = []

    def check(stage_name: str, project_root: Path, *, workflow_profile: str = "full", state_root=None):
        calls.append((stage_name, project_root, workflow_profile, state_root))
        return ("original criterion is unmet",)

    monkeypatch.setattr(stages, "stage_completion_issues", check)
    state, execution = tmp_path / "state", tmp_path / "execution"
    execution.mkdir()
    persist_vertical(state, vertical, workflow_profile="full")
    # Model an existing mid-workflow task, not a new selection's first stage.
    selected = read_pipeline_state(state)
    selected["current_stage"] = stage
    write_pipeline_state(state, selected)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    gathered = collect_round_evidence(RoundEvidenceRequest(execution, state / "handoffs/task", 1))
    host, = [item for item in gathered if item.provider == "argus_verticals.hardware.shared.review:round_evidence"]
    assert calls == [(stage, execution, "full", state)]
    assert "original criterion is unmet" in host.reviewer_text
    assert "original criterion is unmet" in host.engineer_note
    assert "not Reviewer approval" in host.reviewer_text
    assert before == {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("error", [OSError("unreadable original"), ValueError("invalid original")])
def test_host_checker_errors_are_visible_evidence(tmp_path, monkeypatch, error):
    from argus_verticals.digital_circuit.verification import stages

    def check(stage, root, *, workflow_profile="full"):
        raise error

    monkeypatch.setattr(stages, "stage_completion_issues", check)
    persist_vertical(tmp_path, "digital_circuit_verification", workflow_profile="simulation")
    result = round_evidence(RoundEvidenceRequest(tmp_path, tmp_path / ".argus/life", 1))
    assert result is not None
    assert f"completion checker unavailable: {error}" in result.reviewer_text
    assert str(error) in result.engineer_note
    assert '"issues": []' not in result.reviewer_text


def test_host_rejects_a_stage_outside_the_saved_scope(tmp_path):
    persist_vertical(tmp_path, "digital_circuit_verification", workflow_profile="plan")
    state = read_pipeline_state(tmp_path)
    state["current_stage"] = "simulation"
    write_pipeline_state(tmp_path, state)
    result = round_evidence(RoundEvidenceRequest(tmp_path, tmp_path / ".argus/life", 1))
    assert result is not None
    assert "not in the saved workflow scope" in result.reviewer_text


@pytest.mark.parametrize("vertical,profile", [
    ("chip_design", "control"),
    ("chip_design", "architecture"),
    ("digital_circuit", "specification"),
    ("software", None),
])
def test_host_does_not_duplicate_control_or_claim_unrelated_checks(tmp_path, vertical, profile):
    persist_vertical(tmp_path, vertical, workflow_profile=profile)
    assert round_evidence(RoundEvidenceRequest(tmp_path, tmp_path / ".argus/life", 1)) is None


@pytest.mark.parametrize("vertical", ["chip_design", "digital_circuit", "fpga_design"])
@pytest.mark.parametrize("role,operation", [
    ("manager", "stage_decision"), ("planner", "plan_preview"),
    ("engineer", "mission"), ("reviewer", "evaluate"),
])
def test_all_verification_roles_receive_precision_and_continuation_boundaries(tmp_path, vertical, role, operation):
    from argus_verticals.chip_design import stages as chip_stages

    persist_vertical(tmp_path, vertical, workflow_profile="verification")
    prompt = resolve_role_prompt(RolePromptRequest(
        role=RoleName(role), operation=operation, project_root=tmp_path,
        stage="verification", checklist_mode=ChecklistMode.STAGE,
    ))
    assert verification_review_contract() in prompt.role_banner
    assert "unmeasured" in prompt.role_banner
    assert "claim" in prompt.role_banner
    assert "Rerun decisive commands" not in prompt.role_banner
    assert "rerun the declared commands" not in prompt.role_banner
    assert Path(chip_stages.__file__).with_name("control-contract.md").read_text() not in prompt.role_banner
    assert chip_stages.control_check_command() not in prompt.role_banner
    assert "from argus_verticals.chip_design.control import run" not in prompt.role_banner
    assert prompt.stage_order == ("verification",)


@pytest.mark.parametrize("vertical,stage", SPECIALISTS)
@pytest.mark.parametrize("role,operation", [
    ("manager", "stage_decision"), ("planner", "plan_preview"),
    ("engineer", "mission"), ("reviewer", "evaluate"),
])
def test_specialist_roles_receive_host_review_without_accelerator_work(tmp_path, vertical, stage, role, operation):
    from argus_verticals.hardware.shared.review import hardware_review_contract

    persist_vertical(tmp_path, vertical, workflow_profile=stage)
    prompt = resolve_role_prompt(RolePromptRequest(
        role=RoleName(role), operation=operation, project_root=tmp_path,
        stage=stage, checklist_mode=ChecklistMode.STAGE,
    ))
    assert hardware_review_contract() in prompt.role_banner
    assert "Reviewer does not need shell permission" in " ".join(prompt.role_banner.split())
    assert "Accelerator precision" not in prompt.role_banner
    assert "For Engineer debugging or an execution-capable operator" in prompt.role_banner
    assert prompt.stage_order == (stage,)


@pytest.mark.parametrize("vertical,_stage", SPECIALISTS)
def test_specialist_reviewer_skills_do_not_reintroduce_shell_requirements(vertical, _stage):
    from argus.skills.builtins import iter_vertical_skill_texts

    texts = [text for name, text in iter_vertical_skill_texts(vertical) if name.startswith("reviewer/")]
    assert texts
    for text in texts:
        assert "host-executed" in text and "read/search-only" in text
        assert "Run the supplied" not in text
