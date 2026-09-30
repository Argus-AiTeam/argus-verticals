from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import numpy as np
import pytest
from argus.skills.stage_machine import StageCompletionError, complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.rf_design import stages
from argus_verticals.rf_design.evidence import PLAN, RESULTS, validate_analysis, validate_model
from argus_verticals.rf_design.networks import build_networks, read_touchstone
from argus_verticals.rf_design.robustness import ASSESSMENT, inspect_study
from argus_verticals.rf_design.run_analysis import run_analysis
from argus_verticals.rf_design.run_robustness_reference import prepare_reference, run_reference
from argus_verticals.rf_design.study import resolve_study

SPEC = "design/rf-study.json"


def load(root, path=SPEC):
    return json.loads((root / path).read_text())


def save(root, value, path=SPEC):
    (root / path).write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    root = tmp_path_factory.mktemp("rf-corners") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    return Path(shutil.copytree(reference, tmp_path / "work"))


def independent_lmatch(frequencies, inductance, capacitance):
    omega = 2*math.pi*frequencies
    a, b, c, d = 1-omega**2*inductance*capacitance, 1j*omega*inductance, 1j*omega*capacitance, 1
    denominator = 100*a+b+5000*c+50*d
    return (100*a+b-5000*c-50*d)/denominator, 2*math.sqrt(5000)/denominator


def test_complete_real_network_exports_match_independent_complex_equations(reference, tmp_path):
    report = validate_analysis(reference)
    assert report["task_accepted"] and report["status"] == "passed" and report["conclusion_valid"]
    assert report["coverage"]["cartesian_points"] == 4
    assert report["coverage"]["expected_scenarios"] == 5
    assert len(report["coverage"]["completed_cases"]) == len(report["runs"]) == 10
    assert len(report["comparisons"]) == 15
    result = load(reference, RESULTS)
    for row in result["cases"]:
        network = read_touchstone(reference, row["studies"][0]["path"])
        expected_s11, expected_s21 = independent_lmatch(network.f, row["parameters"]["series_l"], row["parameters"]["shunt_c"])
        np.testing.assert_allclose(network.s[:, 0, 0], expected_s11, rtol=1e-12, atol=1e-14)
        np.testing.assert_allclose(network.s[:, 1, 0], expected_s21, rtol=1e-12, atol=1e-14)
        assert len(network.f) == (5 if row["resolution"] == "coarse" else 9)
    state = tmp_path / "state"
    persist_vertical(state, "rf_design", workflow_profile="analysis")
    complete_final_stage(state, reason="complete original finite RF samples", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "rf_design")["ok"]


@pytest.mark.parametrize("goal", ["diagnose", "design"])
def test_nominal_pass_does_not_hide_failed_corners(planned, tmp_path, goal):
    spec = load(planned)
    spec["goal"] = goal
    for axis in spec["axes"]:
        axis["factors"] = [0.8, 1.2]
    save(planned, spec)
    if goal == "design":
        with pytest.raises(EvidenceError, match="failed original limits"):
            run_analysis(planned)
    else:
        run_analysis(planned)
    report = inspect_study(planned)
    assert report["status"] == "failed" and report["conclusion_valid"]
    assert report["task_accepted"] is (goal == "diagnose")
    assert report["failures"] and all(row["kind"] in ("limit", "margin") for row in report["failures"])
    assert all(row["scenario"] != "nominal" for row in report["failures"])
    assert any(row["kind"] == "limit" and row["check"] == "reflection" for row in report["failures"])
    state = tmp_path / "state"
    persist_vertical(state, "rf_design", workflow_profile="analysis")
    if goal == "diagnose":
        complete_final_stage(state, reason="valid diagnosis retains failed original limits", evidence_root=planned)
    else:
        with pytest.raises(StageCompletionError):
            complete_final_stage(state, reason="must not certify failed design", evidence_root=planned)
    with pytest.raises(FileExistsError):
        run_analysis(planned)


def test_required_margin_is_separate_from_original_limit(planned):
    spec = load(planned)
    spec["goal"] = "diagnose"
    spec["studies"][0]["checks"][0]["margin_upper"] = 0.1
    save(planned, spec)
    report = run_analysis(planned)
    assert report["task_accepted"] and report["status"] == "failed"
    assert report["failures"] and all(row["kind"] == "margin" for row in report["failures"])
    assert all(row["within_limits"] for row in report["failures"])


def test_common_design_is_shared_by_all_samples_without_editing_originals(planned):
    spec, plan = load(planned), load(planned, PLAN)
    nominal = spec["parameters"]["series_l"]["nominal"]
    spec["design_variables"] = {"series_l": {"minimum": nominal*0.9, "maximum": nominal*1.1, "source": "Original common design range."}}
    plan["robustness"]["design"] = {"series_l": nominal*0.98}
    save(planned, spec)
    save(planned, plan, PLAN)
    before = (planned / SPEC).read_bytes()
    report = run_analysis(planned)
    assert report["task_accepted"] and report["design"] == plan["robustness"]["design"]
    for scenario in report["coverage"]["scenarios"]:
        factor = scenario["coordinates"].get("series_l_tolerance", 1)
        assert scenario["parameters"]["series_l"] == pytest.approx(nominal*0.98*factor, rel=1e-15)
    assert (planned / SPEC).read_bytes() == before


def test_frequency_refinement_failure_cannot_be_accepted_as_diagnosis(planned):
    spec = load(planned)
    spec["goal"] = "diagnose"
    spec["networks"]["match"]["frequency_hz"] = [0.8e9, 1.2e9]
    check = spec["studies"][0]["checks"][0]
    check.update(statistic="min", max_delta=0.0001)
    check.pop("margin_upper")
    spec["studies"][0]["checks"] = [check]
    save(planned, spec)
    with pytest.raises(EvidenceError, match="numerical validity"):
        run_analysis(planned)
    report = inspect_study(planned)
    assert not report["conclusion_valid"] and not report["task_accepted"]
    assert any(row["kind"] == "refinement" and row["scenario"] == "nominal" for row in report["failures"])


def test_two_frequency_samples_do_not_reinterpret_unequal_port_references(planned):
    spec = load(planned)
    nodes = spec["networks"]
    nodes["match"]["frequency_hz"] = [0.8e9, 1.2e9]
    nodes["changed_reference"] = {"kind": "renormalize", "input": "match", "z0_ohm": [40, 80]}
    networks, _ = build_networks(planned, nodes)
    assert networks["match"].z0.tolist() == [[50, 100], [50, 100]]
    assert networks["changed_reference"].z0.tolist() == [[40, 80], [40, 80]]
    nodes["round_trip"] = {"kind": "renormalize", "input": "changed_reference", "z0_ohm": [50, 100]}
    networks, _ = build_networks(planned, nodes)
    np.testing.assert_allclose(networks["match"].s, networks["round_trip"].s, rtol=1e-12, atol=1e-14)


@pytest.mark.parametrize("mutation", [
    "mixed_legacy", "missing_goal", "bad_goal", "duplicate_target", "bad_index", "bad_target",
    "wrong_unit", "wrong_nominal", "invalid_range", "unknown_variable", "out_of_design",
    "diagnosis_retune", "duplicate_axis", "bad_axis_parameter", "zero_factor", "bool_factor",
    "nan_factor", "duplicate_factor", "out_of_validity", "too_many_corners", "missing_source",
    "bad_check_unit", "unknown_check_field", "negative_margin", "impossible_margin", "negative_delta",
    "interpolated_position", "single_frequency", "too_many_studies",
])
def test_malformed_or_incomplete_specifications_fail_before_results(planned, mutation):
    spec, plan = load(planned), load(planned, PLAN)
    parameter = spec["parameters"]["series_l"]
    check = spec["studies"][0]["checks"][0]
    if mutation == "mixed_legacy":
        plan["studies"] = []
    elif mutation == "missing_goal":
        spec.pop("goal")
    elif mutation == "bad_goal":
        spec["goal"] = []
    elif mutation == "duplicate_target":
        spec["parameters"]["another"] = dict(parameter)
    elif mutation == "bad_index":
        parameter["element"] = True
    elif mutation == "bad_target":
        parameter["network"] = []
    elif mutation == "wrong_unit":
        parameter["unit"] = "F"
    elif mutation == "wrong_nominal":
        parameter["nominal"] *= 1.01
    elif mutation == "invalid_range":
        parameter["minimum"] = parameter["maximum"]*2
    elif mutation in ("unknown_variable", "out_of_design", "diagnosis_retune"):
        name = "unknown" if mutation == "unknown_variable" else "series_l"
        spec["design_variables"] = {name: {"minimum": parameter["nominal"]*0.9, "maximum": parameter["nominal"]*1.1, "source": "Original range."}}
        plan["robustness"]["design"] = {name: parameter["nominal"]*(2 if mutation == "out_of_design" else 1)}
        if mutation == "diagnosis_retune":
            spec["goal"] = "diagnose"
    elif mutation == "duplicate_axis":
        spec["axes"].append(dict(spec["axes"][0]))
    elif mutation == "bad_axis_parameter":
        spec["axes"][0]["parameter"] = []
    elif mutation in ("zero_factor", "bool_factor", "nan_factor", "duplicate_factor", "out_of_validity"):
        spec["axes"][0]["factors"] = [1, {"zero_factor": 0, "bool_factor": True, "nan_factor": float("nan"),
                                       "duplicate_factor": 1, "out_of_validity": 5}[mutation]]
    elif mutation == "too_many_corners":
        for axis in spec["axes"]:
            axis["factors"] = [0.9, 0.95, 1, 1.05, 1.1]
    elif mutation == "missing_source":
        spec["axes"][0]["source"] = ""
    elif mutation == "bad_check_unit":
        check["unit"] = "dB"
    elif mutation == "unknown_check_field":
        check["tolerance"] = 10
    elif mutation == "negative_margin":
        check["margin_lower"] = -1
    elif mutation == "impossible_margin":
        check["margin_upper"] = 1
    elif mutation == "negative_delta":
        check["max_delta"] = -1
    elif mutation == "interpolated_position":
        check["window_hz"][0] = 0.85e9
    elif mutation == "single_frequency":
        spec["networks"]["match"]["frequency_hz"] = [1e9]
    else:
        spec["studies"] *= 5
    save(planned, spec)
    save(planned, plan, PLAN)
    with pytest.raises(EvidenceError):
        run_analysis(planned)
    assert not (planned / RESULTS).exists()


@pytest.mark.parametrize("mutation", ["source", "copy", "case", "model", "export", "assessment", "versions", "status", "goal"])
def test_independent_checker_rejects_changed_evidence(work, mutation):
    result = load(work, RESULTS)
    row = result["cases"][0]
    if mutation == "source":
        (work / SPEC).write_text((work / SPEC).read_text() + "\n")
    elif mutation == "copy":
        (work / result["inputs"][SPEC]).unlink()
    elif mutation == "case":
        result["cases"].pop()
    elif mutation == "model":
        value = load(work, row["model"])
        value["match"]["elements"][0]["value_si"] *= 0.9
        save(work, value, row["model"])
        shutil.copyfile(work / row["model"], work / result["outputs"][row["model"]])
    elif mutation == "export":
        path = row["studies"][0]["path"]
        network = read_touchstone(work, path)
        network.s *= 0.99
        (work / path).write_text(network.write_touchstone(return_string=True, version="2.0", write_noise=False))
        shutil.copyfile(work / path, work / result["outputs"][path])
    elif mutation == "assessment":
        report = load(work, ASSESSMENT)
        report["checks"][0]["worst_observed_upper"]["frequency_hz"] = 123
        save(work, report, ASSESSMENT)
    elif mutation == "versions":
        result["versions"]["scikit-rf"] = "invented"
    elif mutation == "status":
        result["status"] = "failed"
    else:
        result["goal"] = "diagnose"
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError):
        validate_analysis(work)


def test_worst_frequency_and_headroom_are_recomputed_from_saved_complex_fields(reference):
    report = inspect_study(reference)
    worst = report["checks"][0]["worst_observed_upper"]
    result = load(reference, RESULTS)
    row = next(row for row in result["cases"] if row["id"] == worst["case"])
    network = read_touchstone(reference, row["studies"][0]["path"])
    index = np.argmax(np.abs(network.s[:, 0, 0]))
    assert worst["frequency_hz"] == network.f[index]
    assert worst["value"] == abs(network.s[index, 0, 0])
    assert worst["upper_headroom"] == 0.25-worst["value"]
    assert worst["upper_margin_surplus"] == worst["upper_headroom"]-0.01


def test_model_review_and_readonly_evidence_are_distinct(reference):
    assert validate_model(reference)
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    assert inspect_study(reference)["task_accepted"]
    assert stages.stage_completion_issues("review", reference)
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}


def test_decimal_factor_at_exact_validity_boundary_and_nominal_deduplication(planned):
    spec = load(planned)
    node = spec["networks"]["match"]
    node["elements"] = [{"kind": "R", "connection": "series", "value_si": 3}]
    spec["parameters"] = {
        "resistance": {"network": "match", "element": 1, "nominal": 3, "minimum": 1,
                       "maximum": 3.3, "unit": "ohm", "source": "Exact original decimal limit."},
    }
    spec["axes"] = [{"id": "tolerance", "parameter": "resistance", "unit": "1",
                     "factors": [1, 1.1], "source": "Exact original factors."}]
    spec["studies"][0]["checks"] = [{
        "id": "reflection", "requirement": "band", "metric": "s_magnitude", "ports": [1, 1],
        "statistic": "max", "window_hz": [0.8e9, 1.2e9], "minimum": 0, "maximum": 1,
        "unit": "1", "max_delta": 0,
    }]
    save(planned, spec)
    report = run_analysis(planned)
    assert report["coverage"]["cartesian_points"] == report["coverage"]["expected_scenarios"] == 2
    assert report["coverage"]["scenarios"][-1]["parameters"]["resistance"] == 3.3
    assert len(report["runs"]) == 4


def test_selected_closure_does_not_execute_unrelated_measured_models(planned):
    spec = load(planned)
    spec["networks"]["unused"] = {"kind": "touchstone", "path": "missing.s2p"}
    save(planned, spec)
    assert run_analysis(planned)["task_accepted"]
    with pytest.raises(EvidenceError):
        validate_model(planned)


def test_measured_touchstone_cannot_be_invented_into_a_finer_experiment(planned):
    spec = load(planned)
    (planned / "design/measured.s2p").write_text(
        "# Hz S RI R 50\n800000000 0 0 1 0 1 0 0 0\n1200000000 0 0 1 0 1 0 0 0\n"
    )
    spec["networks"]["match"] = {
        "kind": "touchstone", "path": "design/measured.s2p", "ports": ["left", "right"],
        "source": "Supplied samples.", "validity": "Two explicit samples.", "limitations": ["Not an ideal primitive."],
    }
    save(planned, spec)
    with pytest.raises(EvidenceError, match="not interpolated measured"):
        run_analysis(planned)
    assert not (planned / RESULTS).exists()


def test_midpoint_must_be_a_distinct_representable_frequency(planned):
    spec = load(planned)
    spec["networks"]["match"]["frequency_hz"] = [1e9, float(np.nextafter(1e9, math.inf))]
    save(planned, spec)
    with pytest.raises(EvidenceError, match="midpoint"):
        resolve_study(planned)


@pytest.mark.parametrize("kind", ["entries", "output"])
def test_aggregate_budgets_fail_explicitly_without_dropping_cases(planned, monkeypatch, kind):
    from argus_verticals.rf_design import robustness, study

    if kind == "entries":
        monkeypatch.setattr(study, "MAX_SCATTERING_ENTRIES", 1)
        with pytest.raises(EvidenceError, match="scattering entries"):
            run_analysis(planned)
        assert not (planned / RESULTS).exists()
    else:
        monkeypatch.setattr(robustness, "MAX_OUTPUT_BYTES", 1)
        with pytest.raises(EvidenceError, match="aggregate budget"):
            run_analysis(planned)
        assert load(planned, RESULTS)["status"] == "failed"
        assert not (planned / ASSESSMENT).exists()


def test_source_change_during_freeze_cannot_select_different_limits(planned, monkeypatch):
    from argus_verticals.rf_design import robustness

    copy = robustness.shutil.copyfile

    def changed_copy(source, destination, *args, **kwargs):
        if Path(source) == planned / SPEC:
            spec = load(planned)
            spec["studies"][0]["checks"][0]["maximum"] = 0.24
            save(planned, spec)
        return copy(source, destination, *args, **kwargs)

    monkeypatch.setattr(robustness.shutil, "copyfile", changed_copy)
    with pytest.raises(EvidenceError, match="changed while copying"):
        run_analysis(planned)
    assert load(planned, RESULTS)["status"] == "failed"
    assert not (planned / ASSESSMENT).exists()
