from __future__ import annotations

import json
import shutil
import subprocess
from itertools import combinations
from pathlib import Path

import numpy as np
import pytest
from argus.skills.stage_machine import StageCompletionError, complete_final_stage, current_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.analog_mixed_signal import raw as analog_raw
from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.hardware.spice import raw as shared_raw
from argus_verticals.power_electronics import native, stages
from argus_verticals.power_electronics.evidence import validate_simulation
from argus_verticals.power_electronics.model import PLAN, RESULTS, validate_model, validate_plan
from argus_verticals.power_electronics.run_analysis import run_analysis
from argus_verticals.power_electronics.run_reference import (
    prepare_reference,
    reference_voltage,
    run_reference,
)
from argus_verticals.power_electronics.waveform import measurements, product_integral


def load(root, relative=PLAN):
    return json.loads((root / relative).read_text())


def save(root, value, relative=PLAN):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if shutil.which("ngspice") is None:
        pytest.skip("native ngspice is required")
    root = tmp_path_factory.mktemp("power") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture
def buck(planned):
    plan = load(planned)
    plan["runs"] = plan["runs"][:2]
    plan["convergence"] = [p for p in plan["convergence"] if p["coarse"].startswith("buck")]
    plan["requirements"] = {"buck_behavior": plan["requirements"]["buck_behavior"]}
    save(planned, plan)
    return planned


@pytest.fixture
def work(reference, tmp_path):
    root = Path(shutil.copytree(reference, tmp_path / "work"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(reference), str(root)))
    return root


def update_plan_copy(root):
    result = load(root, RESULTS)
    shutil.copyfile(root / PLAN, root / result["inputs"][PLAN])


def test_shared_reader_preserves_analog_public_imports():
    assert analog_raw.Plot is shared_raw.Plot
    assert analog_raw.read_plot is shared_raw.read_plot
    assert analog_raw.measure is shared_raw.measure
    assert analog_raw.PLOT_NAMES == shared_raw.PLOT_NAMES


def test_native_references_and_finite_completion(reference, tmp_path):
    values = validate_simulation(reference)
    plan, models, _ = validate_plan(reference)
    result = load(reference, RESULTS)
    assert len(result["runs"]) == 4 and len(result["outputs"]) == 16
    assert result["ngspice_version"] == native.version()
    for run in plan["runs"]:
        current = values[run["id"]]
        model = models[run["model"]]
        assert current["startup"]["storage_rate_w"] > 0.1
        assert current["startup"]["output_max_v"] > current["before"]["output_mean_v"]
        assert current["after"]["output_power_w"] > 1.5 * current["before"]["output_power_w"]
        assert current["after"]["output_mean_v"] < current["before"]["output_mean_v"]
        for window, resistance in (("before", run["load_resistance_ohm"]), ("after", run["load_step"]["resistance_ohm"])):
            tolerance = 0.02 if model["topology"] == "buck" else 0.1
            assert current[window]["output_mean_v"] == pytest.approx(reference_voltage(model, run, resistance), abs=tolerance)
            assert current[window]["inductor_min_a"] > 0
            assert current[window]["cycle_mean_relative_change"] <= 0.005
        for window in current.values():
            assert window["energy_relative_error"] <= 1e-3
            assert window["input_power_w"] - window["output_power_w"] - window["loss_power_w"] == pytest.approx(
                window["storage_rate_w"], abs=window["input_power_w"] * 1e-3,
            )
    state = tmp_path / "state"
    persist_vertical(state, "power_electronics", workflow_profile="simulation")
    complete_final_stage(state, reason="native converter reference conditions checked", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "power_electronics")["ok"]
    assert not (reference / "power/REVIEW.md").exists()


def test_all_scopes_and_model_only_requirements(planned):
    contract = load_vertical_contract("power_electronics")
    assert stages.VERTICAL_SKILL_PARENTS == ()
    for count in range(1, 5):
        for selected in combinations(stages.STAGE_ORDER, count):
            expected = set(selected) | ({"simulation"} if "review" in selected else set())
            assert contract.compose_workflow(selected).stage_order == tuple(s for s in stages.STAGE_ORDER if s in expected)
    plan = load(planned)
    plan.pop("runs")
    save(planned, plan)
    assert not stages.stage_completion_issues("model", planned)
    plan.pop("models")
    save(planned, plan)
    assert not stages.stage_completion_issues("specification", planned)
    assert stages.stage_completion_issues("simulation", planned)


def test_selected_models_only_and_explicit_review(buck, tmp_path):
    plan = load(buck)
    plan["models"].append("missing.json")
    save(buck, plan)
    _, _, inputs = validate_plan(buck)
    assert inputs == ["design/buck.json", PLAN]
    with pytest.raises(EvidenceError):
        validate_model(buck)
    state = tmp_path / "state"
    persist_vertical(state, "power_electronics", workflow_profile="simulation")
    with pytest.raises(StageCompletionError):
        complete_final_stage(state, reason="no simulation")


def test_review_document_and_no_overwrite(work):
    assert stages.stage_completion_issues("review", work)
    (work / "power/REVIEW.md").write_text("Only the stated native model was checked; no physical qualification.\n")
    assert not stages.stage_completion_issues("review", work)
    with pytest.raises(FileExistsError):
        run_analysis(work)


@pytest.mark.parametrize("change", ["input", "duty", "inductor", "load_step"])
def test_real_physical_changes_fail_unchanged_original_limits(buck, change):
    if change == "inductor":
        model = load(buck, "design/buck.json")
        model["inductance_h"] *= 2
        save(buck, model, "design/buck.json")
    else:
        plan = load(buck)
        for run in plan["runs"]:
            if change == "input":
                run["input_voltage_v"] = 14
            elif change == "duty":
                run["duty_cycle"] = 0.6
            else:
                run["load_step"]["resistance_ohm"] = run["load_resistance_ohm"]
        save(buck, plan)
    with pytest.raises(EvidenceError, match="outside original bounds|not steady"):
        run_analysis(buck)
    result = load(buck, RESULTS)
    assert result["status"] == "failed" and result["runs"]
    assert (buck / "power/results/native/buck_coarse/wave.raw").stat().st_size > 1000
    with pytest.raises(FileExistsError):
        run_analysis(buck)


def test_time_integrals_are_not_sample_averages_or_trapezoids_of_products():
    time = np.array([0.0, 0.1, 1.0])
    assert product_integral(time, time, time) == pytest.approx(1 / 3)
    assert product_integral(time, time, np.ones(3)) == pytest.approx(0.5)
    assert np.mean(time) != pytest.approx(0.5)
    time = np.array([0.0, 0.02, 0.9, 1.0])
    assert product_integral(time, 2 * time + 1, 3 * time + 4) == pytest.approx(11.5)


def test_declaring_an_unsettled_window_steady_fails(work):
    plan = load(work)
    for run in plan["runs"][:2]:
        run["windows"]["before"]["interval_s"] = [0.0001, 0.0005]
    save(work, plan)
    update_plan_copy(work)
    with pytest.raises(EvidenceError, match="not steady"):
        validate_simulation(work)


@pytest.mark.parametrize("mutation", [
    "stale_input", "self_copy", "hardlink", "missing_wave", "failed_status", "wrong_version",
    "wrong_command", "wrong_cwd", "boolean_exit", "duplicate_run", "missing_output_copy",
])
def test_stale_missing_or_forged_records_fail(work, mutation):
    result = load(work, RESULTS)
    if mutation == "stale_input":
        path = work / "design/buck.json"
        path.write_text(path.read_text() + " ")
    elif mutation == "self_copy":
        result["inputs"][PLAN] = PLAN
    elif mutation == "hardlink":
        path = work / result["inputs"][PLAN]
        path.unlink()
        path.hardlink_to(work / PLAN)
    elif mutation == "missing_wave":
        (work / "power/results/native/buck_coarse/wave.raw").unlink()
    elif mutation == "failed_status":
        result["status"] = "failed"
    elif mutation == "wrong_version":
        result["ngspice_version"] = "0"
    elif mutation == "wrong_command":
        result["runs"][0]["execution"]["command"] = ["echo", "success"]
    elif mutation == "wrong_cwd":
        result["runs"][0]["execution"]["cwd"] = "/tmp"
    elif mutation == "boolean_exit":
        result["runs"][0]["execution"]["exit_code"] = False
    elif mutation == "duplicate_run":
        result["runs"][1] = result["runs"][0]
    else:
        result["outputs"].pop(next(iter(result["outputs"])))
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError):
        validate_simulation(work)


@pytest.mark.parametrize("mutation", ["circuit", "wave", "units", "diagnostic"])
def test_matching_altered_copies_do_not_establish_native_truth(work, mutation):
    result = load(work, RESULTS)
    relative = "power/results/native/buck_coarse/" + (
        "model.cir" if mutation == "circuit" else "ngspice.log" if mutation == "diagnostic" else "wave.raw"
    )
    path = work / relative
    content = path.read_text()
    if mutation == "circuit":
        content = content.replace("Vin in 0 DC 12", "Vin in 0 DC 14")
    elif mutation == "wave":
        lines = content.splitlines()
        lines[lines.index("Values:") + 3] = "\t1.000000000000000e-09"
        content = "\n".join(lines) + "\n"
    elif mutation == "units":
        content = content.replace("v(out)\tvoltage", "v(out)\tcurrent")
    else:
        content += "\nError: artificial zero-exit native failure\n"
    assert content != path.read_text()
    path.write_text(content)
    shutil.copyfile(path, work / result["outputs"][relative])
    with pytest.raises(EvidenceError):
        validate_simulation(work)


@pytest.mark.parametrize("mutation", [
    "bool_input", "nan_duty", "overflow_frequency", "duty_bound", "step_too_large", "too_many_points",
    "output_bound", "power_bound", "unknown_model", "unknown_field", "bad_step_type", "late_step",
    "empty_windows", "zero_start", "short_window", "noninteger_steady", "steady_crosses_load",
    "load_window_misses_step", "startup_late", "unknown_window", "unused_window", "wrong_unit",
    "metric_type", "reversed_bounds", "unknown_requirement", "missing_comparison",
    "different_physics", "not_finer", "negative_delta", "duplicate_pair", "unknown_pair",
    "model_topology", "model_unknown_field", "model_zero_l", "model_bool_c", "model_no_source",
])
def test_invalid_models_plans_windows_and_refinement_are_rejected(buck, mutation):
    plan = load(buck)
    run = plan["runs"][0]
    if mutation == "bool_input":
        run["input_voltage_v"] = True
    elif mutation == "nan_duty":
        run["duty_cycle"] = float("nan")
    elif mutation == "overflow_frequency":
        run["frequency_hz"] = 10**1000
    elif mutation == "duty_bound":
        run["duty_cycle"] = 0.99
    elif mutation == "step_too_large":
        run["max_step_s"] = 1e-5
    elif mutation == "too_many_points":
        run["max_step_s"] = 2e-8
    elif mutation == "output_bound":
        model = load(buck, "design/buck.json")
        model["topology"] = "boost"
        save(buck, model, "design/buck.json")
        run["input_voltage_v"] = 48
    elif mutation == "power_bound":
        run["load_resistance_ohm"] = 0.1
    elif mutation == "unknown_model":
        run["model"] = "missing.json"
    elif mutation == "unknown_field":
        run["external_deck"] = "untracked.cir"
    elif mutation == "bad_step_type":
        run["load_step"] = []
    elif mutation == "late_step":
        run["load_step"]["time_s"] = 0.004
    elif mutation == "empty_windows":
        run["windows"] = {}
    elif mutation == "zero_start":
        run["windows"]["startup"]["interval_s"][0] = 0
    elif mutation == "short_window":
        run["windows"]["before"]["interval_s"] = [0.001, 0.001001]
    elif mutation == "noninteger_steady":
        run["windows"]["before"]["interval_s"] = [0.001, 0.001501]
    elif mutation == "steady_crosses_load":
        run["windows"]["before"]["interval_s"] = [0.0019, 0.0023]
    elif mutation == "load_window_misses_step":
        run["windows"]["transition"]["interval_s"] = [0.003, 0.004]
    elif mutation == "startup_late":
        run["windows"]["startup"]["interval_s"][0] = 0.0001
    elif mutation == "unknown_window":
        run["checks"][0]["window"] = "absent"
    elif mutation == "unused_window":
        run["windows"]["extra"] = {"kind": "steady", "interval_s": [0.003, 0.004]}
    elif mutation == "wrong_unit":
        run["checks"][0]["unit"] = "mV"
    elif mutation == "metric_type":
        run["checks"][0]["metric"] = []
    elif mutation == "reversed_bounds":
        run["checks"][0].update(minimum=20, maximum=10)
    elif mutation == "unknown_requirement":
        run["checks"][0]["requirement"] = "absent"
    elif mutation == "missing_comparison":
        plan["convergence"] = []
    elif mutation == "different_physics":
        plan["runs"][1]["input_voltage_v"] = 13
    elif mutation == "not_finer":
        plan["runs"][1]["max_step_s"] = 1.5e-7
    elif mutation == "negative_delta":
        plan["convergence"][0]["max_delta"] = -1
    elif mutation == "duplicate_pair":
        plan["convergence"] *= 2
    elif mutation == "unknown_pair":
        plan["convergence"][0]["fine"] = "absent"
    else:
        model = load(buck, "design/buck.json")
        if mutation == "model_topology":
            model["topology"] = "flyback"
        elif mutation == "model_unknown_field":
            model["core_saturation"] = True
        elif mutation == "model_zero_l":
            model["inductance_h"] = 0
        elif mutation == "model_bool_c":
            model["capacitance_f"] = False
        else:
            model["source"] = ""
        save(buck, model, "design/buck.json")
    save(buck, plan)
    with pytest.raises(EvidenceError):
        validate_plan(buck)


def test_original_time_step_delta_is_not_relaxed(work):
    plan = load(work)
    pair = next(p for p in plan["convergence"] if p["window"] == "after" and p["metric"] == "output_mean_v")
    pair["max_delta"] = 0
    save(work, plan)
    update_plan_copy(work)
    with pytest.raises(EvidenceError, match="comparison delta"):
        validate_simulation(work)


@pytest.mark.parametrize("bound", ["time", "output"])
def test_native_resource_limits_stop_and_preserve_failure(buck, monkeypatch, bound):
    monkeypatch.setattr(native, "TIMEOUT_SECONDS" if bound == "time" else "MAX_OUTPUT_BYTES", 0 if bound == "time" else 1)
    with pytest.raises(EvidenceError, match="exceeded"):
        run_analysis(buck)
    result = load(buck, RESULTS)
    assert result["status"] == "failed"
    assert result["runs"][0]["execution"]["exit_code"] != 0
    assert (buck / "power/results/native/buck_coarse/model.cir").exists()


def test_missing_tool_is_an_explicit_failure(buck, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(EvidenceError, match="native ngspice is required"):
        run_analysis(buck)
    assert not (buck / RESULTS).exists()


@pytest.mark.parametrize("code,banner", [(0, "ngspice-41"), (0, "unrecognized"), (1, "ngspice-42")])
def test_unsupported_tool_response_is_not_success(monkeypatch, code, banner):
    monkeypatch.setattr(native.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], code, banner, ""))
    with pytest.raises(EvidenceError, match="requires native ngspice"):
        native.version()


def test_checker_is_read_only_and_metrics_are_native(reference):
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    values = validate_simulation(reference)
    plan, models, _ = validate_plan(reference)
    run = plan["runs"][0]
    plot = shared_raw.read_plot(reference / "power/results/native/buck_coarse/wave.raw", "tran")
    assert measurements(plot, models[run["model"]], run) == values[run["id"]]
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}


def test_real_role_builders_include_the_canonical_contract(tmp_path):
    from argus.roles.prompts import resolve_role_prompt
    from argus.roles.prompts.engineer import mission_request
    from argus.roles.prompts.manager import stage_decision_request
    from argus.roles.prompts.planner import PLAN_PREVIEW, continuous_request
    from argus.roles.prompts.reviewer import evaluate_request

    state, project = tmp_path / "state", tmp_path / "project"
    project.mkdir()
    persist_vertical(state, "power_electronics", workflow_profile="simulation")
    requests = [
        stage_decision_request(state, stage=current_stage(state)),
        continuous_request(state, operation=PLAN_PREVIEW, altitude_root=project, include_search_altitude=False),
        mission_request(state, altitude_root=project, stage=current_stage(state)),
        evaluate_request(state, altitude_root=project),
    ]
    canonical = Path(stages.__file__).with_name("evidence-contract.md").read_text()
    for request in requests:
        prompt = resolve_role_prompt(request)
        assert prompt.stage_order == ("simulation",)
        assert canonical in prompt.role_banner
        assert stages.evidence_check_command("power_electronics", "simulation") in prompt.role_banner
