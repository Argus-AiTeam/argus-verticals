from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from argus.skills.stage_machine import StageCompletionError, complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.digital_circuit.verification import stages
from argus_verticals.digital_circuit.verification.evidence import (
    EvidenceError,
    validate_formal,
    validate_simulation,
    verification_evidence_contract,
)
from argus_verticals.digital_circuit.verification.run_reference import run_reference


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if not all(shutil.which(tool) for tool in ("iverilog", "vvp")):
        pytest.skip("Icarus Verilog is required for the executable reference")
    root = tmp_path_factory.mktemp("verification") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    return Path(shutil.copytree(reference, tmp_path / "work"))


def edit_json(root, relative, mutate):
    path = root / relative
    value = json.loads(path.read_text())
    mutate(value)
    path.write_text(json.dumps(value))


def test_real_regression_completes_only_the_selected_specialty_scope(reference, tmp_path):
    state = tmp_path / "state"
    persist_vertical(state, "digital_circuit_verification", workflow_profile="simulation")
    complete_final_stage(state, reason="independent regression reviewed", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "digital_circuit_verification")["ok"]
    assert load_vertical_contract("digital_circuit_verification", state).stage_order == ("simulation",)
    result = json.loads((reference / "verification/RESULTS.json").read_text())
    assert len(result["runs"]) == 12
    assert not (reference / "verification/FORMAL.json").exists()


def test_missing_simulation_does_not_complete(tmp_path):
    persist_vertical(tmp_path, "digital_circuit_verification", workflow_profile="simulation")
    with pytest.raises(StageCompletionError):
        complete_final_stage(tmp_path, reason="unexecuted")


@pytest.mark.parametrize("mutation", ["missing_plan", "legacy_shape", "missing_run", "duplicate_run", "bad_exit", "zero_checks", "false_pass", "changed_source", "changed_plan", "self_snapshot", "external_snapshot"])
def test_regression_rejects_incomplete_or_contradictory_evidence(work, tmp_path, mutation):
    result = json.loads((work / "verification/RESULTS.json").read_text())
    if mutation == "missing_plan":
        (work / "verification/PLAN.json").unlink()
    elif mutation == "legacy_shape":
        result = {"configurations": [{"result": "PASS", "cycles": 500}]}
    elif mutation == "missing_run":
        result["runs"].pop()
    elif mutation == "duplicate_run":
        result["runs"].append(result["runs"][0])
    elif mutation == "bad_exit":
        result["runs"][0]["exit_code"] = True
    elif mutation in {"zero_checks", "false_pass"}:
        log = work / result["runs"][0]["log"]
        text = log.read_text()
        if mutation == "zero_checks":
            text = "\n".join("CHECK transfer 0" if line.startswith("CHECK transfer ") else line for line in text.splitlines()) + "\n"
        else:
            text += "FATAL broken design\n"
        log.write_text(text)
    elif mutation == "changed_source":
        (work / "rtl/stream_fifo.sv").write_text("module wrong; endmodule")
    elif mutation == "changed_plan":
        edit_json(work, "verification/PLAN.json", lambda plan: plan["configurations"].pop())
    elif mutation == "self_snapshot":
        result["inputs"]["rtl/stream_fifo.sv"] = "rtl/stream_fifo.sv"
    else:
        outside = tmp_path / "outside.sv"
        shutil.copyfile(work / "rtl/stream_fifo.sv", outside)
        result["inputs"]["rtl/stream_fifo.sv"] = "../outside.sv"
    (work / "verification/RESULTS.json").write_text(json.dumps(result))
    with pytest.raises(EvidenceError):
        validate_simulation(work)


@pytest.mark.parametrize("role, operation", [
    ("manager", "stage_decision"), ("planner", "plan_preview"),
    ("engineer", "mission"), ("reviewer", "evaluate"),
])
@pytest.mark.parametrize("stage", ["plan", "simulation", "formal", "review"])
def test_runtime_roles_receive_the_canonical_evidence_contract(tmp_path, role, operation, stage):
    from argus.roles.prompts import ChecklistMode, RoleName, RolePromptRequest, resolve_role_prompt

    state = tmp_path / "state"
    persist_vertical(
        state, "digital_circuit_verification",
        workflow_profile="full" if stage == "review" else stage,
    )
    prompt = resolve_role_prompt(RolePromptRequest(
        role=RoleName(role), operation=operation, project_root=state,
        stage=stage, checklist_mode=ChecklistMode.STAGE,
    ))
    assert verification_evidence_contract() in prompt.role_banner
    assert stages.evidence_check_command("digital_circuit_verification", stage) in prompt.role_banner
    assert "Reviewer: independently inspect the oracle and run the checker" in prompt.role_banner
    assert "not the internal session-state directory" in prompt.role_banner
    assert prompt.stage_order == (stages.STAGE_ORDER if stage == "review" else (stage,))


def test_private_rtl_mutation_is_detected_by_the_real_scoreboard(work):
    source = work / "rtl/stream_fifo.sv"
    source.write_text(source.read_text().replace("assign out_data = mem[rd];", "assign out_data = ~mem[rd];"))
    compile_result = subprocess.run(
        ["iverilog", "-g2012", "-s", "stream_fifo_tb", "-o", "broken.vvp", "rtl/stream_fifo.sv", "tb/stream_fifo_tb.sv"],
        cwd=work, capture_output=True, text=True, timeout=30,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run(["vvp", "broken.vvp", "+SEED=1"], cwd=work, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0
    assert "ordering/data mismatch" in result.stdout


def test_existing_reference_destination_is_never_overwritten(work):
    with pytest.raises(FileExistsError):
        run_reference(work)
    validate_simulation(work)

@pytest.mark.parametrize("parameter", ["WIDTH", "DEPTH"])
def test_illegal_reference_parameter_is_rejected(work, parameter):
    compiled = subprocess.run(
        ["iverilog", "-g2012", "-s", "stream_fifo_tb", f"-Pstream_fifo_tb.{parameter}=0",
         "-o", "illegal.vvp", "rtl/stream_fifo.sv", "tb/stream_fifo_tb.sv"],
        cwd=work, capture_output=True, text=True, timeout=30,
    )
    if compiled.returncode == 0:
        result = subprocess.run(["vvp", "illegal.vvp", "+SEED=1"], cwd=work, capture_output=True, text=True, timeout=30)
        assert result.returncode != 0
        assert "illegal FIFO parameters" in result.stdout


def test_formal_checks_require_reached_covers_and_declared_assumptions(work):
    plan = json.loads((work / "verification/PLAN.json").read_text())
    plan["formal"] = {
        "mode": "prove", "depth": 20, "assertions": ["ordering"], "covers": ["traffic"],
        "assumptions": [{"expression": "initial reset", "reason": "external reset contract"}],
    }
    (work / "verification/PLAN.json").write_text(json.dumps(plan))
    results = json.loads((work / "verification/RESULTS.json").read_text())
    shutil.copyfile(work / "verification/PLAN.json", work / results["inputs"]["verification/PLAN.json"])
    # Synthetic native output exercises the checker, not an actual proof.
    (work / "verification/prove.log").write_text("SBY test: DONE (PASS, rc=0)\n")
    (work / "verification/cover.vcd").write_text("$comment synthetic witness for record test $end\n")
    run = {"command": ["sby", "-f", "properties.sby"], "exit_code": 0, "log": "verification/prove.log", "depth": 20}
    formal = {
        "inputs": results["inputs"],
        "assertions": {"ordering": {**run, "mode": "prove"}},
        "covers": {"traffic": {**run, "mode": "cover", "witness": "verification/cover.vcd"}},
    }
    (work / "verification/FORMAL.json").write_text(json.dumps(formal))
    validate_formal(work)
    formal["covers"]["traffic"].pop("witness")
    (work / "verification/FORMAL.json").write_text(json.dumps(formal))
    with pytest.raises(EvidenceError, match="file"):
        validate_formal(work)
    formal["covers"]["traffic"]["witness"] = "verification/cover.vcd"
    formal["assertions"]["ordering"]["mode"] = "bmc"
    (work / "verification/FORMAL.json").write_text(json.dumps(formal))
    with pytest.raises(EvidenceError, match="mode/depth"):
        validate_formal(work)


def test_all_specialty_subsets_preserve_mandatory_companions():
    from itertools import combinations

    from argus.core.vertical_contract import vertical_contract

    contract = vertical_contract("digital_circuit_verification", stages)
    for size in range(1, len(stages.STAGE_ORDER) + 1):
        for goals in combinations(stages.STAGE_ORDER, size):
            selected = contract.compose_workflow(goals)
            expected = set(stages.STAGE_ORDER) if "review" in goals else set(goals)
            assert selected.stage_order == tuple(stage for stage in stages.STAGE_ORDER if stage in expected)
