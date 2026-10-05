from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
from argus.skills.stage_machine import StageCompletionError, complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.digital_circuit.verification import cdc, cdc_model, cdc_simulation, stages
from argus_verticals.digital_circuit.verification.cdc_model import (
    ASSESSMENT,
    DIRECTORY,
    PLAN,
    RESULTS,
)
from argus_verticals.digital_circuit.verification.evidence import (
    EvidenceError,
    validate_plan,
    validate_simulation,
)
from argus_verticals.digital_circuit.verification.run_cdc_reference import (
    prepare_reference as prepare,
)
from argus_verticals.digital_circuit.verification.run_cdc_reference import run_reference


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if any(shutil.which(tool) is None for tool in ("yosys", "iverilog", "vvp")):
        pytest.skip("native Yosys and Icarus Verilog are required")
    root = tmp_path_factory.mktemp("cdc") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def fresh(reference, tmp_path):
    root = tmp_path / "project"
    prepare(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    return Path(shutil.copytree(reference, tmp_path / "work"))


def edit(root, relative, change):
    path = root / relative
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def retained(root, relative):
    result = json.loads((root / RESULTS).read_text())
    shutil.copyfile(root / relative, root / result["outputs"][relative])


def test_native_positive_scope_and_read_only_replay(reference, tmp_path):
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    report = cdc.validate(reference)
    assert report["status"] == "passed" and report["goal"] == "design" and report["task_accepted"]
    assert len(report["structure"]["chains"]) == 3
    assert all(v["passed"] and all(c["comparisons"] > 0 and c["mismatches"] == 0 for c in v["checks"].values()) for v in report["simulations"].values())
    persist_vertical(tmp_path / "state", "digital_circuit_verification", workflow_profile="cdc")
    complete_final_stage(tmp_path / "state", reason="independent native structures and traces reviewed", evidence_root=reference)
    assert vertical_completion_certificate_status(tmp_path / "state", "digital_circuit_verification")["ok"]
    assert load_vertical_contract("digital_circuit_verification", tmp_path / "state").stage_order == ("simulation",)
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    assert not (reference / "verification/FORMAL.json").exists()
    result = subprocess.run(shlex.split(stages.cdc_check_command()), cwd=reference, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0 and result.stdout.strip() == "[]", result.stdout + result.stderr


MUTATIONS = [
    ("early_stage", "assign level_out = capture[1];", "assign level_out = capture[0];"),
    ("wrong_clock", "posedge clk_dst or negedge reset_dst_n", "posedge clk_src or negedge reset_dst_n"),
    ("combinational_capture", "{capture[0], launch}", "{capture[0], ~launch}"),
    ("unlaunched_input", "{capture[0], launch}", "{capture[0], level_in}"),
    ("synchronous_assert", "posedge clk_dst or negedge arst_n", "posedge clk_dst"),
    ("asynchronous_release", "assign reset_dst_n = reset_dst[1];", "assign reset_dst_n = arst_n;"),
    ("early_reset_stage", "assign reset_dst_n = reset_dst[1];", "assign reset_dst_n = reset_dst[0];"),
    ("raw_capture_reset", "posedge clk_dst or negedge reset_dst_n)\n        if (!reset_dst_n)", "posedge clk_dst or negedge arst_n)\n        if (!arst_n)"),
]


@pytest.mark.parametrize("name,old,new", MUTATIONS)
def test_real_bad_rtl_supports_negative_diagnosis_not_design(fresh, name, old, new, tmp_path):
    source = fresh / "rtl/cdc_reference.sv"
    assert old in source.read_text()
    source.write_text(source.read_text().replace(old, new))
    edit(fresh, "design/cdc-study.json", lambda s: s.update(goal="diagnose"))
    report = cdc.run(fresh)
    assert report["status"] == "failed" and report["task_accepted"] and report["conclusion_valid"]
    assert not report["structure"]["passed"]
    if name == "raw_capture_reset":
        assert all(v["passed"] for v in report["simulations"].values())
    else:
        assert any(not v["passed"] for v in report["simulations"].values())
    assert cdc.validate(fresh) == report
    with pytest.raises(EvidenceError, match="must pass"):
        cdc.validate(fresh, require_pass=True)
    design = tmp_path / "design"
    prepare(design)
    (design / "rtl/cdc_reference.sv").write_bytes(source.read_bytes())
    with pytest.raises(EvidenceError, match="violates"):
        cdc.run(design)
    assert json.loads((design / RESULTS).read_text())["status"] == "failed"
    assert not json.loads((design / ASSESSMENT).read_text())["task_accepted"]
    assert (design / DIRECTORY / "source_fast.simulate.log").is_file()


def test_structure_catches_unconsumed_early_stage_fanout(fresh):
    source = fresh / "rtl/cdc_reference.sv"
    text = source.read_text().replace("assign level_out = capture[1];", "assign level_out = capture[1];\n    (* keep *) reg leaked;\n    always @(posedge clk_dst or negedge reset_dst_n)\n        if (!reset_dst_n) leaked <= 0; else leaked <= capture[0];")
    source.write_text(text)
    edit(fresh, "design/cdc-study.json", lambda s: s.update(goal="diagnose"))
    report = cdc.run(fresh)
    assert report["status"] == "failed" and all(v["passed"] for v in report["simulations"].values())
    assert any("fanout" in row for row in report["structure"]["failures"])


def test_three_stage_resets_and_crossing_with_separate_reset_inputs(fresh):
    source = fresh / "rtl/cdc_reference.sv"
    text = source.read_text().replace("input wire arst_n,", "input wire arst_n,\n    input wire arst_dst_n,")
    text = text.replace("posedge clk_dst or negedge arst_n)\n        if (!arst_n)", "posedge clk_dst or negedge arst_dst_n)\n        if (!arst_dst_n)")
    text = text.replace("[1:0]", "[2:0]").replace("2'b00", "3'b000")
    text = text.replace("{reset_src[0],", "{reset_src[1:0],").replace("{reset_dst[0],", "{reset_dst[1:0],")
    text = text.replace("{capture[0],", "{capture[1:0],").replace("= reset_src[1]", "= reset_src[2]")
    text = text.replace("= reset_dst[1]", "= reset_dst[2]").replace("= capture[1]", "= capture[2]")
    source.write_text(text)
    def change(spec):
        for reset in spec["resets"].values():
            reset["stages"] = 3
        spec["resets"]["clk_dst"]["input"] = "arst_dst_n"
        spec["crossings"]["status_level"]["stages"] = 3
    edit(fresh, "design/cdc-study.json", change)
    assert cdc.run(fresh)["status"] == "passed"
    assert cdc.validate(fresh)["status"] == "passed"


@pytest.mark.parametrize("mutation", [
    "wrong_goal", "one_clock", "missing_reset", "one_stage", "same_clock", "shared_port",
    "missing_configuration_clock", "duplicate_configuration", "bad_phase", "odd_period", "bool_period",
    "unknown_field", "missing_requirement", "escaping_source", "include", "system_task",
])
def test_original_declarations_reject_unsupported_or_ambiguous_inputs(fresh, mutation):
    path = fresh / "design/cdc-study.json"
    spec = json.loads(path.read_text())
    if mutation == "wrong_goal":
        spec["goal"] = "anything"
    elif mutation == "one_clock":
        spec["clocks"].pop()
    elif mutation == "missing_reset":
        spec["resets"].pop("clk_src")
    elif mutation == "one_stage":
        spec["crossings"]["status_level"]["stages"] = 1
    elif mutation == "same_clock":
        spec["crossings"]["status_level"]["source_clock"] = "clk_dst"
    elif mutation == "shared_port":
        spec["crossings"]["status_level"]["input"] = "arst_n"
    elif mutation == "missing_configuration_clock":
        spec["configurations"]["source_fast"].pop("clk_dst")
    elif mutation == "duplicate_configuration":
        spec["configurations"]["source_fast"] = spec["configurations"]["destination_fast"]
    elif mutation in ("bad_phase", "odd_period", "bool_period"):
        timing = spec["configurations"]["source_fast"]["clk_src"]
        timing["phase_ticks" if mutation == "bad_phase" else "period_ticks"] = {"bad_phase": 10, "odd_period": 11, "bool_period": True}[mutation]
    elif mutation == "unknown_field":
        spec["waivers"] = []
    elif mutation == "missing_requirement":
        spec["requirements"].pop("reset_assert")
    elif mutation == "escaping_source":
        spec["sources"] = ["../outside.sv"]
    else:
        source = fresh / "rtl/cdc_reference.sv"
        source.write_text(source.read_text() + ('\n`include "outside.sv"\n' if mutation == "include" else '\nmodule extra; initial $display("unbound"); endmodule\n'))
    path.write_text(json.dumps(spec))
    with pytest.raises(EvidenceError):
        cdc.run(fresh)
    assert not (fresh / DIRECTORY).exists()


@pytest.mark.parametrize("mutation", [
    "changed_source", "changed_spec", "bad_exit", "wrong_command", "missing_command",
    "self_copy", "missing_output", "changed_trace", "forged_assessment", "replaced_netlist", "replaced_testbench",
])
def test_saved_evidence_and_native_replay_reject_replacement(work, mutation):
    result = json.loads((work / RESULTS).read_text())
    if mutation == "changed_source":
        (work / "rtl/cdc_reference.sv").write_text("module changed; endmodule\n")
    elif mutation == "changed_spec":
        edit(work, "design/cdc-study.json", lambda s: s["configurations"]["source_fast"]["clk_dst"].update(phase_ticks=2))
    elif mutation == "bad_exit":
        result["commands"][0]["exit_code"] = True
    elif mutation == "wrong_command":
        result["commands"][0]["command"] = ["echo", "PASS"]
    elif mutation == "missing_command":
        result["commands"].pop()
    elif mutation == "self_copy":
        result["inputs"][PLAN] = PLAN
    elif mutation == "missing_output":
        result["outputs"].pop(ASSESSMENT)
    elif mutation == "changed_trace":
        trace = work / DIRECTORY / "source_fast.simulate.log"
        trace.write_text(trace.read_text().replace("SAMPLE 1 ", "SAMPLE 2 ", 1))
        retained(work, trace.relative_to(work).as_posix())
    elif mutation == "forged_assessment":
        edit(work, ASSESSMENT, lambda s: s.update(status="failed"))
        retained(work, ASSESSMENT)
    elif mutation == "replaced_netlist":
        edit(work, f"{DIRECTORY}/netlist.json", lambda s: s.update(creator="unrelated Yosys"))
        retained(work, f"{DIRECTORY}/netlist.json")
    else:
        tb = work / DIRECTORY / "source_fast.sv"
        tb.write_text(tb.read_text() + "// replaced stimulus\n")
        retained(work, tb.relative_to(work).as_posix())
    (work / RESULTS).write_text(json.dumps(result))
    with pytest.raises(EvidenceError):
        cdc.validate(work)


def test_empty_or_absent_native_results_cannot_complete(tmp_path):
    persist_vertical(tmp_path / "state", "digital_circuit_verification", workflow_profile="cdc")
    with pytest.raises(StageCompletionError):
        complete_final_stage(tmp_path / "state", reason="not executed", evidence_root=tmp_path)


def test_existing_result_is_never_overwritten(reference):
    with pytest.raises(FileExistsError):
        cdc.run(reference)


def test_failed_native_command_keeps_actual_exit_and_output(fresh, monkeypatch):
    monkeypatch.setattr(cdc, "_commands", lambda spec: [("yosys", ["yosys", "-p", "not_a_yosys_command"])])
    with pytest.raises(EvidenceError, match="exited"):
        cdc.run(fresh)
    result = json.loads((fresh / RESULTS).read_text())
    assert result["status"] == "failed" and result["commands"][0]["exit_code"] != 0
    assert "No such command" in (fresh / result["commands"][0]["log"]).read_text()


def test_clock_stimuli_assert_and_release_between_edges(reference):
    spec, _ = cdc_model.resolve(reference)
    for configuration in spec["configurations"].values():
        frames = cdc_simulation.stimulus(spec, configuration)
        transitions = [tick for tick in range(2, len(frames)) if frames[tick]["arst_n"] != frames[tick - 1]["arst_n"]]
        assert len(transitions) == 3
        assert all(not cdc_simulation.rising(tick, timing) for tick in transitions for timing in configuration.values())


def test_oracle_old_value_capture_on_hand_calculated_coincident_edges():
    spec = {
        "resets": {
            "src": {"input": "rst", "output": "src_rst", "stages": 2},
            "dst": {"input": "rst", "output": "dst_rst", "stages": 2},
        },
        "crossings": {
            "level": {"input": "in", "output": "out", "source_clock": "src", "destination_clock": "dst", "stages": 2},
        },
    }
    configuration = {clock: {"period_ticks": 8, "phase_ticks": 0} for clock in ("src", "dst")}
    frames = [{"rst": int(tick != 1), "in": 1} for tick in range(43)]
    observed = cdc_simulation.expected(spec, configuration, frames)
    # Reset starts at tick 1; release edges are 9/17, launch 25, capture 33/41.
    assert [tick for tick in range(1, 43) if observed[tick - 1]["dst_rst"] == 1] == list(range(17, 43))
    assert [tick for tick in range(1, 43) if observed[tick - 1]["out"] == 1] == [41, 42]
    frames[42]["rst"] = 0
    assert cdc_simulation.expected(spec, configuration, frames)[-1] == {"src_rst": 0, "dst_rst": 0, "out": 0}


def test_opt_in_composition_requires_current_cdc_inputs_and_passing_results(work):
    from argus_verticals.digital_circuit.verification.run_reference import run_reference as run_fifo
    fifo = work.parent / "fifo"
    run_fifo(fifo)
    for relative in ("rtl/stream_fifo.sv", "tb/stream_fifo_tb.sv"):
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fifo / relative, target)
    # Copy the real regression's independent evidence without overwriting CDC results.
    shutil.copytree(fifo / "verification", work / "verification", dirs_exist_ok=True)
    edit(work, "verification/PLAN.json", lambda p: (p.update(cdc=True), p["sources"].append("rtl/cdc_reference.sv")))
    result = json.loads((work / "verification/RESULTS.json").read_text())
    required = ["verification/PLAN.json", *cdc_model.resolve(work)[1], RESULTS, ASSESSMENT]
    for relative in required:
        snapshot = f"verification/composed-inputs/{relative}"
        (work / snapshot).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(work / relative, work / snapshot)
        result["inputs"][relative] = snapshot
    (work / "verification/RESULTS.json").write_text(json.dumps(result))
    validate_simulation(work)
    from argus_verticals.fpga_design.evidence import validate_verification

    target = {
        "top": "stream_fifo", "board": "unconnected logic-only reference", "part": "up5k", "package": "sg48",
        "clock": {"port": "clk", "frequency_mhz": 12}, "sources": ["rtl/stream_fifo.sv", "rtl/cdc_reference.sv"],
        "pins": {"clk": "1"}, "io_voltage_v": 3.3, "limitations": ["No board or implementation claim"],
    }
    (work / "design/FPGA_TARGET.json").write_text(json.dumps(target))
    snapshot = "verification/composed-inputs/target.json"
    shutil.copyfile(work / "design/FPGA_TARGET.json", work / snapshot)
    result["inputs"]["design/FPGA_TARGET.json"] = snapshot
    (work / "verification/RESULTS.json").write_text(json.dumps(result))
    validate_verification(work)
    result["inputs"].pop(ASSESSMENT)
    (work / "verification/RESULTS.json").write_text(json.dumps(result))
    with pytest.raises(EvidenceError, match="snapshots"):
        validate_verification(work)
    edit(work, "verification/PLAN.json", lambda p: p["sources"].remove("rtl/cdc_reference.sv"))
    with pytest.raises(EvidenceError, match="CDC sources"):
        validate_plan(work)


def test_legacy_full_profile_does_not_force_cdc():
    assert stages.WORKFLOW_PROFILES["full"]["stages"] == ("plan", "simulation", "formal", "review")


@pytest.mark.parametrize("role,operation", [
    ("manager", "stage_decision"), ("planner", "plan_preview"),
    ("engineer", "mission"), ("reviewer", "evaluate"),
])
def test_cdc_profile_roles_receive_original_contract_and_correct_checker(tmp_path, role, operation):
    from argus.roles.prompts import ChecklistMode, RoleName, RolePromptRequest, resolve_role_prompt

    from argus_verticals.digital_circuit.verification.evidence import verification_evidence_contract

    persist_vertical(tmp_path, "digital_circuit_verification", workflow_profile="cdc")
    prompt = resolve_role_prompt(RolePromptRequest(
        role=RoleName(role), operation=operation, project_root=tmp_path,
        stage="simulation", checklist_mode=ChecklistMode.STAGE,
    ))
    assert prompt.stage_order == ("simulation",)
    assert verification_evidence_contract() in prompt.role_banner
    assert stages.cdc_check_command() in prompt.role_banner
    assert "no general PLAN.json or formal evidence is required" in prompt.role_banner
