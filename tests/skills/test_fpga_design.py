from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from argus.skills.stage_machine import advance_stage, complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.digital_circuit.verification.evidence import EvidenceError
from argus_verticals.fpga_design import stages
from argus_verticals.fpga_design.evidence import (
    TARGET,
    validate_bringup,
    validate_implementation,
    validate_verification,
)
from argus_verticals.fpga_design.run_implementation import run_implementation

RTL = """module blink(input wire clk, output wire led);
reg [7:0] count = 0;
always @(posedge clk) count <= count + 1'b1;
assign led = count[7];
endmodule
"""
TB = """module blink_tb;
reg clk = 0;
wire led;
blink dut(clk, led);
always #5 clk = !clk;
initial begin
  for (integer n = 1; n <= 600; n = n+1) begin
    @(posedge clk); #1;
    if (led !== ((n % 256) >= 128)) $fatal(1, "divider mismatch");
  end
  $display("CHECK transfer 600");
  $display("PASS regression");
  $finish;
end
endmodule
"""


def save(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n" if not isinstance(value, str) else value)


def snapshot(root, relative, directory="verification/inputs"):
    copy = f"{directory}/{relative}"
    (root / copy).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / relative, root / copy)
    return copy


@pytest.mark.parametrize("role, operation", [
    ("manager", "stage_decision"), ("planner", "plan_preview"),
    ("engineer", "mission"), ("reviewer", "evaluate"),
])
def test_fpga_verification_reuses_the_same_runtime_record_contract(tmp_path, role, operation):
    from argus.roles.prompts import ChecklistMode, RoleName, RolePromptRequest, resolve_role_prompt

    from argus_verticals.digital_circuit.verification.evidence import verification_evidence_contract

    persist_vertical(tmp_path, "fpga_design", workflow_profile="verification")
    prompt = resolve_role_prompt(RolePromptRequest(
        role=RoleName(role), operation=operation, project_root=tmp_path,
        stage="verification", checklist_mode=ChecklistMode.STAGE,
    ))
    assert verification_evidence_contract() in prompt.role_banner
    assert "Also snapshot design/FPGA_TARGET.json" in prompt.role_banner
    assert stages.evidence_check_command("fpga_design", "verification") in prompt.role_banner
    assert prompt.stage_order == ("verification",)


@pytest.fixture(scope="module")
def verified(tmp_path_factory):
    if not all(shutil.which(tool) for tool in ("iverilog", "vvp")):
        pytest.skip("Icarus Verilog is required for RTL verification")
    root = tmp_path_factory.mktemp("fpga-verified")
    target = {
        "top": "blink", "board": "unconnected iCEstick reference target", "part": "hx1k", "package": "tq144",
        "clock": {"port": "clk", "frequency_mhz": 12}, "sources": ["rtl/blink.sv"],
        "pins": {"clk": "21", "led": "99"}, "io_voltage_v": 3.3,
        "limitations": ["No physical board measurements"],
        "bringup_checks": {"led_frequency_hz": {"minimum": 46000, "maximum": 48000}},
    }
    save(root, TARGET, target)
    save(root, "rtl/blink.sv", RTL)
    save(root, "tb/blink_tb.sv", TB)
    save(root, "constraints/board.pcf", "set_io clk 21\nset_io led 99\n")
    plan = {
        "sources": ["rtl/blink.sv"], "testbenches": ["tb/blink_tb.sv"], "configurations": ["8bit"],
        "cases": ["transfer"], "requirements": {"divide by 256": ["transfer"]},
    }
    save(root, "verification/PLAN.json", plan)
    compile_command = ["iverilog", "-g2012", "-s", "blink_tb", "-o", "verification/blink.vvp", *plan["sources"], *plan["testbenches"]]
    subprocess.run(compile_command, cwd=root, capture_output=True, check=True, timeout=30)
    command = ["vvp", "verification/blink.vvp"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True, timeout=30)
    save(root, "verification/blink.log", result.stdout + result.stderr)
    inputs = {relative: snapshot(root, relative) for relative in [TARGET, "verification/PLAN.json", *plan["sources"], *plan["testbenches"]]}
    save(root, "verification/RESULTS.json", {
        "inputs": inputs,
        "runs": [{"configuration": "8bit", "command": command, "exit_code": 0, "log": "verification/blink.log", "compile_command": compile_command}],
    })
    validate_verification(root)
    return root


@pytest.fixture(scope="module")
def implemented(verified, tmp_path_factory):
    if not all(shutil.which(tool) for tool in ("yosys", "nextpnr-ice40", "icepack")):
        pytest.skip("Yosys, nextpnr-ice40 and IceStorm are required for native implementation")
    root = Path(shutil.copytree(verified, tmp_path_factory.mktemp("fpga-build") / "project"))
    run_implementation(root)
    return root


@pytest.fixture
def work(implemented, tmp_path):
    return Path(shutil.copytree(implemented, tmp_path / "work"))


def test_real_rtl_only_scope_finishes_without_implementation_or_board(verified, tmp_path):
    persist_vertical(tmp_path, "fpga_design", workflow_profile="rtl")
    advance_stage(tmp_path, target_stage="rtl", reason="target reviewed", evidence_root=verified)
    advance_stage(tmp_path, target_stage="verification", reason="RTL reviewed", evidence_root=verified)
    complete_final_stage(tmp_path, reason="oracle passed", evidence_root=verified)
    assert vertical_completion_certificate_status(tmp_path, "fpga_design")["ok"]
    assert not (verified / "implementation").exists()
    assert not (verified / "bringup").exists()


def test_host_checks_target_bound_verification_without_building_or_programming(verified, tmp_path):
    from argus.engineer.round_evidence import RoundEvidenceRequest, collect_round_evidence

    persist_vertical(tmp_path, "fpga_design", workflow_profile="verification")
    before = {p.relative_to(verified): p.read_bytes() for p in verified.rglob("*") if p.is_file()}
    gathered = collect_round_evidence(RoundEvidenceRequest(verified, tmp_path / "handoffs/task", 1))
    host, = [item for item in gathered if item.provider == "argus_verticals.hardware.shared.review:round_evidence"]
    assert '"issues": []' in host.reviewer_text
    assert not host.engineer_note
    assert before == {p.relative_to(verified): p.read_bytes() for p in verified.rglob("*") if p.is_file()}
    assert not (verified / "implementation").exists()


def test_real_native_implementation_finishes_without_board(implemented, tmp_path):
    persist_vertical(tmp_path, "fpga_design", workflow_profile="implementation")
    advance_stage(tmp_path, target_stage="implementation", reason="verified", evidence_root=implemented)
    complete_final_stage(tmp_path, reason="native reports reviewed", evidence_root=implemented)
    assert vertical_completion_certificate_status(tmp_path, "fpga_design")["ok"]
    assert (implemented / "implementation/design.bin").stat().st_size > 100
    assert not (implemented / "bringup").exists()


@pytest.mark.parametrize("mutation", ["frequency", "capacity", "nan", "empty_clocks", "extra_clock", "changed_pin", "changed_rtl", "waiver", "missing_bitstream", "changed_bitstream"])
def test_native_implementation_rejects_invalid_results(work, mutation):
    timing = json.loads((work / "implementation/timing.json").read_text())
    clock = next(iter(timing["fmax"].values()))
    if mutation == "frequency":
        clock["achieved"] = 1
    elif mutation == "capacity":
        usage = next(iter(timing["utilization"].values()))
        usage["used"] = usage["available"] + 1
    elif mutation == "nan":
        clock["achieved"] = float("nan")
    elif mutation == "empty_clocks":
        timing["fmax"] = {}
    elif mutation == "extra_clock":
        timing["fmax"]["extra"] = dict(clock)
    elif mutation == "changed_pin":
        (work / "constraints/board.pcf").write_text("set_io clk 21\nset_io led 98\n")
    elif mutation == "changed_rtl":
        (work / "rtl/blink.sv").write_text(RTL + "\n// changed source\n")
    elif mutation == "waiver":
        build = json.loads((work / "implementation/BUILD.json").read_text())
        build["commands"]["place_route"]["command"].append("--timing-allow-fail")
        save(work, "implementation/BUILD.json", build)
    elif mutation == "missing_bitstream":
        (work / "implementation/design.bin").unlink()
    else:
        (work / "implementation/design.bin").write_bytes(b"not the generated bitstream")
    save(work, "implementation/timing.json", timing)
    if mutation in {"frequency", "capacity", "nan", "empty_clocks", "extra_clock"}:
        snapshot(work, "implementation/timing.json", "implementation/native-test-results")
        build = json.loads((work / "implementation/BUILD.json").read_text())
        build["outputs"]["implementation/timing.json"] = "implementation/native-test-results/implementation/timing.json"
        save(work, "implementation/BUILD.json", build)
    with pytest.raises(EvidenceError):
        validate_implementation(work)


def test_bringup_cannot_substitute_a_build_for_measurement(implemented):
    with pytest.raises(EvidenceError, match="bringup"):
        validate_bringup(implemented)


@pytest.mark.parametrize("measurement", ["nan", "inf", "0", "49000", "47000"])
def test_bringup_measurement_limits_on_synthetic_records(work, measurement):
    # No physical execution is claimed; these are parser/boundary fixtures.
    save(work, "bringup/measure.log", f"MEASURE led_frequency_hz {measurement}\n")
    target = json.loads((work / TARGET).read_text())
    save(work, "bringup/RESULTS.json", {
        "board": target["board"], "device_id": "synthetic-unit-test-only", "connection": "fixture",
        "programming_permission": "synthetic unit test; no device programmed",
        "inputs": {relative: snapshot(work, relative, "bringup/inputs") for relative in [TARGET, "implementation/design.bin", "implementation/BUILD.json"]},
        "measurement": {"command": ["fixture-reader"], "exit_code": 0, "log": "bringup/measure.log"},
    })
    if measurement == "47000":
        validate_bringup(work)
    else:
        with pytest.raises(EvidenceError):
            validate_bringup(work)


def test_missing_tools_fail_before_creating_output(verified, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="yosys is required"):
        run_implementation(verified)
    assert not (verified / "implementation").exists()


def test_fpga_custom_goals_add_only_required_companions(tmp_path):
    persist_vertical(tmp_path, "fpga_design", workflow_profile="custom", workflow_requested_stages=("rtl", "implementation"))
    assert load_vertical_contract("fpga_design", tmp_path).stage_order == ("requirements", "rtl", "verification", "implementation")
    assert stages.stage_completion_issues("bringup", tmp_path)
