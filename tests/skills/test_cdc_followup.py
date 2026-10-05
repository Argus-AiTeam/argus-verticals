from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import pytest

from argus_verticals.digital_circuit.verification import cdc, cdc_model, cdc_simulation
from argus_verticals.digital_circuit.verification.cdc_model import DIRECTORY, RESULTS
from argus_verticals.digital_circuit.verification.evidence import EvidenceError
from argus_verticals.digital_circuit.verification.run_cdc_reference import prepare_reference


@pytest.fixture
def work(tmp_path):
    if any(shutil.which(tool) is None for tool in ("yosys", "iverilog", "vvp")):
        pytest.skip("native Yosys and Icarus Verilog are required")
    root = tmp_path / "project"
    prepare_reference(root)
    return root


def two_paths(root: Path, *, swap: bool) -> dict:
    source = root / "rtl/cdc_reference.sv"
    text = source.read_text().replace("input wire level_in,", "input wire level_in,\n    input wire level_two,")
    text = text.replace("output wire level_out", "output wire other_out,\n    output wire level_out")
    text = text.replace("endmodule", """
    reg launch_two;
    reg [1:0] capture_two;
    always @(posedge clk_src or negedge reset_src_n)
        if (!reset_src_n) launch_two <= 0;
        else launch_two <= level_two;
    always @(posedge clk_dst or negedge reset_dst_n)
        if (!reset_dst_n) capture_two <= 0;
        else capture_two <= {capture_two[0], launch_two};
    assign other_out = capture_two[1];
endmodule
""")
    if swap:
        text = text.replace("else launch <= level_in;", "else launch <= level_two;")
        text = text.replace("else launch_two <= level_two;", "else launch_two <= level_in;")
    source.write_text(text)
    path = root / "design/cdc-study.json"
    spec = json.loads(path.read_text())
    spec["goal"] = "diagnose" if swap else "design"
    spec["crossings"]["other_level"] = {
        **spec["crossings"]["status_level"], "input": "level_two", "output": "other_out",
    }
    path.write_text(json.dumps(spec))
    return spec


def test_swapped_levels_are_observable_in_every_native_configuration(work):
    two_paths(work, swap=True)
    report = cdc.run(work)
    assert not report["structure"]["passed"]
    assert all(not row["passed"] for row in report["simulations"].values())
    assert all(row["checks"]["level_latency"]["mismatches"] > 0 for row in report["simulations"].values())
    assert cdc.validate(work) == report


def test_independent_levels_settle_before_reset_recovery(work):
    spec = two_paths(work, swap=False)
    report = cdc.run(work)
    assert report["status"] == "passed"
    for configuration in spec["configurations"].values():
        frames = cdc_simulation.stimulus(spec, configuration)
        observed = cdc_simulation.expected(spec, configuration, frames)
        assert {(f["level_in"], f["level_two"]) for f in frames} == {(0, 0), (0, 1), (1, 0), (1, 1)}
        assert {(f["level_out"], f["other_out"]) for f in observed} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert cdc.validate(work) == report


def test_structural_mismatch_identifies_cell_port_and_expected_actual_net(work):
    source = work / "rtl/cdc_reference.sv"
    source.write_text(source.read_text().replace(
        "posedge clk_dst or negedge reset_dst_n)\n        if (!reset_dst_n)",
        "posedge clk_src or negedge arst_n)\n        if (!arst_n)",
    ))
    path = work / "design/cdc-study.json"
    spec = json.loads(path.read_text())
    spec["goal"] = "diagnose"
    path.write_text(json.dumps(spec))
    report = cdc.run(work)
    findings = report["structure"].get("findings", [])
    clock = next(f for f in findings if f["kind"] == "clock" and f["path"] == "crossing.status_level")
    reset = next(f for f in findings if f["kind"] == "reset" and f["path"] == "crossing.status_level")
    assert clock["expected"] == "clk_dst" and "clk_src" in clock["observed"]
    assert reset["expected"] == "reset_dst_n" and "arst_n" in reset["observed"]
    assert clock["cell"] == reset["cell"] and clock["bit"] == reset["bit"] == 1


@pytest.mark.parametrize("reason", ["output", "production_output", "timeout"])
def test_native_limit_stops_running_child_and_records_actual_exit(work, monkeypatch, reason):
    spec, _ = cdc_model.resolve(work)
    (work / DIRECTORY).mkdir()
    if reason == "output":
        script = "import sys,time; print('x'*2097152,flush=True); time.sleep(1); print('UNSTOPPED')"
        monkeypatch.setattr(cdc, "OUTPUT_BUDGET", 1024 * 1024, raising=False)
    elif reason == "production_output":
        assert cdc.OUTPUT_BUDGET == 128 * 1024 * 1024
        script = ("import time; f=open('verification/cdc/oversized.bin','wb'); "
                  "f.truncate(129*1024*1024); f.close(); time.sleep(1); print('UNSTOPPED')")
    else:
        script = "import time; time.sleep(1); print('UNSTOPPED')"
        monkeypatch.setattr(cdc, "COMMAND_TIMEOUT", 0.1, raising=False)
    monkeypatch.setattr(cdc, "_commands", lambda spec: [("probe", [sys.executable, "-c", script])])
    result = {"commands": []}
    with pytest.raises(EvidenceError, match="output|seconds"):
        cdc._execute(work, spec, result)
    saved = json.loads((work / RESULTS).read_text())["commands"][0]
    assert type(saved["exit_code"]) is int and saved["exit_code"] < 0
    assert saved["stop_reason"]
    assert "UNSTOPPED" not in (work / saved["log"]).read_text().splitlines()


def test_failed_chain_does_not_hide_other_bad_stage(work):
    source = work / "rtl/cdc_reference.sv"
    text = source.read_text()
    text = text.replace(
        "always @(posedge clk_dst or negedge reset_dst_n)\n"
        "        if (!reset_dst_n) capture <= 2'b00;\n"
        "        else capture <= {capture[0], launch};",
        "always @(posedge clk_src or negedge reset_dst_n)\n"
        "        if (!reset_dst_n) capture[1] <= 0; else capture[1] <= capture[0];\n"
        "    always @(posedge clk_dst or negedge arst_n)\n"
        "        if (!arst_n) capture[0] <= 0; else capture[0] <= launch;",
    )
    source.write_text(text)
    spec = json.loads((work / "design/cdc-study.json").read_text())
    spec["goal"] = "diagnose"
    (work / "design/cdc-study.json").write_text(json.dumps(spec))
    report = cdc.run(work)
    findings = report["structure"].get("findings", [])
    assert {"clock", "reset"} <= {f["kind"] for f in findings if f.get("path") == "crossing.status_level"}


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process-group cleanup")
def test_timeout_stops_only_its_owned_process_group(work, monkeypatch):
    child = "import pathlib,time; time.sleep(0.5); pathlib.Path('survived').write_text('wrong')"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(3)"
    monkeypatch.setattr(cdc, "COMMAND_TIMEOUT", 0.15)
    monkeypatch.setattr(cdc, "_commands", lambda spec: [("probe", [sys.executable, "-c", parent])])
    with pytest.raises(EvidenceError, match="seconds"):
        cdc.run(work)
    result = json.loads((work / RESULTS).read_text())
    assert result["status"] == "failed" and result["commands"][0]["exit_code"] < 0
    assert not (work / cdc.ASSESSMENT).exists()
    time.sleep(0.55)
    assert not (work / "survived").exists()


def test_four_input_patterns_distinguish_every_path(work):
    spec = two_paths(work, swap=False)
    for index in (2, 3):
        spec["crossings"][f"extra_{index}"] = {
            **spec["crossings"]["status_level"], "input": f"input_{index}", "output": f"output_{index}",
        }
    inputs = [c["input"] for c in spec["crossings"].values()]
    for configuration in spec["configurations"].values():
        frames = cdc_simulation.stimulus(spec, configuration)
        expected = cdc_simulation.expected(spec, configuration, frames)
        patterns = {tuple(frame[p] for p in inputs) for frame in frames}
        output_patterns = {tuple(row[c["output"]] for c in spec["crossings"].values()) for row in expected}
        for selected in range(4):
            one = tuple(int(index == selected) for index in range(4))
            zero = tuple(1 - value for value in one)
            assert one in patterns and zero in patterns
            assert one in output_patterns and zero in output_patterns


def test_findings_recomputation_rejects_forged_actual_reset(work):
    source = work / "rtl/cdc_reference.sv"
    source.write_text(source.read_text().replace(
        "posedge clk_dst or negedge reset_dst_n)\n        if (!reset_dst_n)",
        "posedge clk_dst or negedge arst_n)\n        if (!arst_n)",
    ))
    spec = json.loads((work / "design/cdc-study.json").read_text())
    spec["goal"] = "diagnose"
    (work / "design/cdc-study.json").write_text(json.dumps(spec))
    cdc.run(work)
    report = json.loads((work / cdc.ASSESSMENT).read_text())
    witness = next(f for f in report["structure"]["findings"] if f["kind"] == "reset")
    witness["observed"] = ["reset_dst_n"]
    (work / cdc.ASSESSMENT).write_text(json.dumps(report))
    result = json.loads((work / RESULTS).read_text())
    shutil.copyfile(work / cdc.ASSESSMENT, work / result["outputs"][cdc.ASSESSMENT])
    with pytest.raises(EvidenceError, match="assessment"):
        cdc.validate(work)


def test_native_vector_aliases_use_declared_ascending_indices(work):
    source = work / "rtl/cdc_reference.sv"
    source.write_text(source.read_text().replace(
        "reg launch;",
        "wire [4:5] reset_alias;\n    assign reset_alias = {reset_dst_n, reset_src_n};\n    reg launch;",
    ).replace(
        "posedge clk_dst or negedge reset_dst_n)\n        if (!reset_dst_n)",
        "posedge clk_dst or negedge reset_alias[5])\n        if (!reset_alias[5])",
    ))
    spec = json.loads((work / "design/cdc-study.json").read_text())
    spec["goal"] = "diagnose"
    (work / "design/cdc-study.json").write_text(json.dumps(spec))
    report = cdc.run(work)
    findings = [f for f in report["structure"]["findings"] if f["kind"] == "reset"]
    assert findings and all("reset_alias[5]" in f["observed"] and "reset_alias[4]" not in f["observed"] for f in findings)
