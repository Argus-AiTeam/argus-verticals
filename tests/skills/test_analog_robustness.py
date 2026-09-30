from __future__ import annotations

import itertools
import json
import math
import shutil
from pathlib import Path

import pytest
from argus.skills.stage_machine import complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status

from argus_verticals.analog_mixed_signal import robustness, stages
from argus_verticals.analog_mixed_signal.evidence import (
    PLAN,
    RESULTS,
    validate_plan,
    validate_simulation,
)
from argus_verticals.analog_mixed_signal.robustness import ASSESSMENT, inspect_study
from argus_verticals.analog_mixed_signal.run_analysis import run_analysis
from argus_verticals.analog_mixed_signal.run_robustness_reference import (
    diode_voltage,
    prepare_reference,
)
from argus_verticals.analog_mixed_signal.study import analysis_grid, resolve_study
from argus_verticals.hardware.shared.evidence import EvidenceError


def load(root, path):
    return json.loads((root / path).read_text())


def save(root, path, value):
    (root / path).write_text(json.dumps(value, indent=2) + "\n")


def small_project(root, *, goal="diagnose", tight=True):
    prepare_reference(root, goal=goal, tight=tight)
    spec = load(root, "design/operating.json")
    spec["axes"] = spec["axes"][:1]
    spec["analyses"] = [analysis for analysis in spec["analyses"] if analysis["kind"] == "ac"]
    save(root, "design/operating.json", spec)
    plan = load(root, PLAN)
    plan["requirements"] = {"frequency": plan["requirements"]["frequency"]}
    save(root, PLAN, plan)
    return root


@pytest.fixture
def planned(tmp_path):
    return small_project(tmp_path / "planned")


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if shutil.which("ngspice") is None:
        pytest.skip("native ngspice is required")
    root = tmp_path_factory.mktemp("analog-envelope") / "reference"
    prepare_reference(root, goal="diagnose", tight=True)
    run_analysis(root)
    return root


@pytest.fixture(scope="module")
def small_reference(tmp_path_factory):
    if shutil.which("ngspice") is None:
        pytest.skip("native ngspice is required")
    root = small_project(tmp_path_factory.mktemp("analog-small") / "reference")
    run_analysis(root)
    return root


@pytest.fixture
def work(small_reference, tmp_path):
    root = Path(shutil.copytree(small_reference, tmp_path / "work"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(small_reference), str(root)))
    return root


def test_full_native_study_matches_independent_physics(reference):
    report = validate_simulation(reference)
    assert report == load(reference, ASSESSMENT)
    assert report["goal"] == "diagnose" and report["status"] == "failed"
    assert report["conclusion_valid"] and report["task_accepted"]
    assert len(report["runs"]) == 136 and len(report["comparisons"]) == 136
    assert report["coverage"]["complete"] and report["coverage"]["expected_scenarios"] == 17
    assert all(row["passed"] for row in report["comparisons"])
    assert report["failures"] and {row["check"] for row in report["failures"]} == {"gain"}
    assert not any(row["run"].startswith("nominal_") for row in report["failures"])
    expected = set(itertools.product([900, 1100], [90e-9, 110e-9], [8000, 12000], [0, 60]))
    actual = {
        (row["parameters"]["resistance"], row["parameters"]["capacitance"],
         row["parameters"]["load"], row["parameters"]["temp_c"])
        for row in report["coverage"]["scenarios"] if row["id"] != "nominal"
    }
    assert len(actual) == len(expected) == 16
    assert all(any(all(math.isclose(a, e, rel_tol=1e-14, abs_tol=1e-15) for a, e in zip(row, target))
                   for target in expected) for row in actual)
    points = {}
    for row in report["runs"]:
        p, values = row["parameters"], row["measurements"]
        gain = p["load"] / (p["resistance"] + p["load"])
        tau = p["resistance"] * gain * p["capacitance"]
        if row["analysis"] == "bias":
            assert values["dc_level"] == pytest.approx(p["input_v"] * gain, abs=1e-8)
            assert values["diode"] == pytest.approx(diode_voltage(p["temp_c"]), abs=1e-4)
            assert row["native_points"] == 1
        elif row["analysis"] == "transfer":
            assert values["midpoint"] == pytest.approx(0.5 * gain, abs=1e-8)
        elif row["analysis"] == "frequency":
            x = 2 * math.pi * 1000 * tau
            assert values["gain"] == pytest.approx(gain / math.sqrt(1+x*x), abs=1e-4)
            assert values["phase"] == pytest.approx(-math.degrees(math.atan(x)), abs=0.03)
            assert values["edge"] == pytest.approx(math.sqrt((gain/0.5)**2-1)/(2*math.pi*tau), abs=2)
        else:
            assert values["response"] == pytest.approx(gain * (1-math.exp(-0.0001/tau)), abs=2e-4)
            assert values["rise"] == pytest.approx(-tau*math.log1p(-0.5/gain), abs=2e-7)
        key = row["scenario"], row["analysis"]
        points.setdefault(key, {})[row["resolution"]] = row["native_points"]
    assert all(pair["fine"] > pair["coarse"] for (_, analysis), pair in points.items() if analysis != "bias")


def test_worst_headroom_and_every_failure_are_recomputed(reference):
    report = load(reference, ASSESSMENT)
    spec = load(reference, "design/operating.json")
    expected_failures = set()
    for analysis in spec["analyses"]:
        relevant = [row for row in report["runs"] if row["analysis"] == analysis["id"]]
        for check in analysis["checks"]:
            lower, upper = [], []
            for row in relevant:
                value = row["measurements"][check["id"]]
                lower.append((value-check["minimum"], row["id"]))
                upper.append((check["maximum"]-value, row["id"]))
                if not check["minimum"] <= value <= check["maximum"]:
                    expected_failures.add((row["id"], check["id"], "limit"))
                elif lower[-1][0] < check.get("margin_lower", 0) or upper[-1][0] < check.get("margin_upper", 0):
                    expected_failures.add((row["id"], check["id"], "margin"))
            summary = next(item for item in report["checks"] if item["analysis"] == analysis["id"] and item["id"] == check["id"])
            assert summary["worst_observed_lower"]["lower_headroom"] == min(value for value, _ in lower)
            assert summary["worst_observed_upper"]["upper_headroom"] == min(value for value, _ in upper)
            assert summary["expected_runs"] == summary["evaluated_runs"] == 34
    assert expected_failures == {(row["run"], row["check"], row["kind"]) for row in report["failures"]}


def test_accepted_diagnosis_reuses_native_evidence_across_report_changes(work, tmp_path, monkeypatch):
    state = tmp_path / "state"
    calls = []
    execute = robustness._execute

    def counted(*args, **kwargs):
        calls.append(args[2].id)
        return execute(*args, **kwargs)

    monkeypatch.setattr(robustness, "_execute", counted)
    before = {p.relative_to(work): p.read_bytes() for p in work.rglob("*") if p.is_file()}
    assert not stages.stage_completion_issues("simulation", work, state_root=state)
    assert len(calls) == 6
    assert before == {p.relative_to(work): p.read_bytes() for p in work.rglob("*") if p.is_file()}
    report = work / "analog/REVIEW.md"
    report.write_text("Finite negative diagnosis, not hardware approval.")
    assert not stages.stage_completion_issues("review", work, state_root=state)
    report.write_text("Clarified: tolerance sensitivity is not a global numerical error bound.")
    assert not stages.stage_completion_issues("review", work, state_root=state)
    assert len(calls) == 6
    final_state = tmp_path / "final-state"
    persist_vertical(final_state, "analog_mixed_signal", workflow_profile="simulation")
    complete_final_stage(final_state, reason="complete finite diagnosis with unchanged original bounds", evidence_root=work)
    assert vertical_completion_certificate_status(final_state, "analog_mixed_signal")["ok"]
    assert len(calls) == 12
    model = work / "design/circuit.inc"
    model.write_text(model.read_text() + "\n")
    assert stages.stage_completion_issues("simulation", work, state_root=state)


def test_design_requires_all_original_limits(tmp_path):
    passing = small_project(tmp_path / "passing", goal="design", tight=False)
    assert run_analysis(passing)["task_accepted"]
    assert not stages.stage_completion_issues("simulation", passing, state_root=tmp_path / "state")
    failing = small_project(tmp_path / "failing", goal="design", tight=True)
    with pytest.raises(EvidenceError, match="not accepted"):
        run_analysis(failing)
    report = inspect_study(failing)
    assert report["conclusion_valid"] and not report["task_accepted"]
    assert stages.stage_completion_issues("simulation", failing, state_root=tmp_path / "failed-state")


def test_common_design_choices_and_nominal_deduplication(tmp_path):
    root = small_project(tmp_path / "design", goal="design", tight=False)
    plan, spec = load(root, PLAN), load(root, "design/operating.json")
    plan["robustness"]["design"]["resistance"] = 1100
    spec["axes"][0]["factors"] = [1, 1.1]
    save(root, PLAN, plan)
    save(root, "design/operating.json", spec)
    study = resolve_study(root)
    assert study.grid_size == len(study.scenarios) == 2
    assert [row["parameters"]["resistance"] for row in study.scenarios] == pytest.approx([1100, 1210])
    assert study.choices == {"resistance": 1100}
    assert validate_plan(root)[1] == list(study.inputs)


@pytest.mark.parametrize("field,value,match", [
    ("goal", "verification", "goal"),
    ("goal", [], "goal"),
    ("relative_tolerances", [1e-4, 1e-4], "fine reltol"),
    ("relative_tolerances", [1e-4, 0], "fine reltol"),
    ("relative_tolerances", [True, 1e-6], "finite number"),
    ("axes", [], "axes"),
    ("analyses", [], "analyses"),
    ("unknown_control", 1, "only"),
])
def test_invalid_external_specification_is_rejected(planned, field, value, match):
    spec = load(planned, "design/operating.json")
    spec[field] = value
    save(planned, "design/operating.json", spec)
    with pytest.raises(EvidenceError, match=match):
        resolve_study(planned)


def test_goal_cannot_be_changed_by_plan_choices(planned):
    spec, plan = load(planned, "design/operating.json"), load(planned, PLAN)
    spec["design_variables"] = {"r": {"parameter": "resistance", "minimum": 900, "maximum": 1100, "source": "choice"}}
    plan["robustness"]["design"] = {"r": 1000}
    save(planned, "design/operating.json", spec)
    save(planned, PLAN, plan)
    with pytest.raises(EvidenceError, match="diagnose fixes"):
        resolve_study(planned)


@pytest.mark.parametrize("edit,match", [
    ("nominal", "nominal specification"),
    ("duplicate", "remain distinct"),
    ("range", "outside declared model"),
    ("temperature_factor", "non-temperature"),
    ("unknown_parameter", "declared parameters"),
    ("both", "either absolute"),
    ("unit", "axis unit"),
])
def test_parameter_samples_are_not_silently_reinterpreted(planned, edit, match):
    spec = load(planned, "design/operating.json")
    axis = spec["axes"][0]
    if edit == "nominal":
        spec["parameters"]["resistance"]["nominal"] = 1050
    elif edit == "duplicate":
        axis["factors"] = [0.9, 0.9]
    elif edit == "range":
        axis["factors"] = [0.1, 10]
    elif edit == "temperature_factor":
        axis["parameter"] = "temp_c"
    elif edit == "unknown_parameter":
        axis["parameter"] = "missing"
    elif edit == "both":
        axis["values"] = [900, 1100]
    else:
        axis["unit"] = "V"
    save(planned, "design/operating.json", spec)
    with pytest.raises(EvidenceError, match=match):
        resolve_study(planned)


@pytest.mark.parametrize("extra", [
    ".param resistance=1000", ".subckt local a b params: resistance=1000",
    "+ resistance=1000", ".options reltol=1e-3", "+ reltol=1e-3",
])
def test_hidden_parameter_or_solver_overrides_are_rejected(planned, extra):
    path = planned / "design/circuit.inc"
    path.write_text(path.read_text() + extra + "\n")
    with pytest.raises(EvidenceError, match="redeclared|conflicting"):
        resolve_study(planned)


def test_complete_grid_is_bounded_without_dropping_combinations(tmp_path):
    root = tmp_path / "too-many"
    prepare_reference(root)
    spec = load(root, "design/operating.json")
    spec["axes"].append({"id": "input", "parameter": "input_v", "unit": "V", "values": [0.9, 1.1], "source": "original"})
    save(root, "design/operating.json", spec)
    with pytest.raises(EvidenceError, match="no combinations were dropped"):
        resolve_study(root)
    assert not (root / "analog/results").exists()


@pytest.mark.parametrize("kind,directive,fragment,points", [
    ("op", ".op", ".op", 1),
    ("dc", ".dc Vin 1 -1 -0.1", "-0.050000000000000003", 41),
    ("ac", ".ac lin 11 10 10000", ".ac lin 21", 21),
    ("ac", ".ac dec 10 10 10000", ".ac dec 20", 61),
    ("ac", ".ac oct 10 1 8", ".ac oct 20", 61),
    ("tran", ".tran 1u 1m 0 1u uic", ".tran", 2033),
])
def test_native_refinement_preserves_range_and_explicit_semantics(kind, directive, fragment, points):
    refined, estimated = analysis_grid("Title\n" + directive + "\n.end\n", kind, fine=True)
    assert fragment in refined
    assert estimated == pytest.approx(points, abs=1)


@pytest.mark.parametrize("kind,directive", [
    ("dc", ".dc Vin 0 1 -0.1"), ("dc", ".dc Vin 0 1 0.3"),
    ("dc", ".dc Vin 0 1 0.1 Iin 0 1 0.1"),
    ("ac", ".ac dec 999999999999999999999999 1 10"),
    ("ac", ".ac dec \u00b2 1 10"),
    ("ac", ".ac dec 100 0 10000"), ("tran", ".tran 1u 1m"),
    ("tran", ".tran 1e-300 1e300 0 1e-300"),
    ("dc", ".dc Vin 0 5e-324 5e-324"), ("tran", ".tran 5e-324 5e-324 0 5e-324"),
])
def test_unsupported_or_unbounded_grids_fail_explicitly(kind, directive):
    with pytest.raises(EvidenceError):
        analysis_grid("Title\n" + directive + "\n.end\n", kind, fine=True)


@pytest.mark.parametrize("failure", ["ambiguous_measurement", "refinement"])
def test_invalid_numerics_do_not_become_successful_diagnoses(planned, failure):
    spec = load(planned, "design/operating.json")
    check = next(check for check in spec["analyses"][0]["checks"] if check["id"] == "edge")
    if failure == "ambiguous_measurement":
        check["level"] = 20
    else:
        check["max_delta"] = 1e-12
    save(planned, "design/operating.json", spec)
    with pytest.raises(EvidenceError, match="not accepted"):
        run_analysis(planned)
    report = load(planned, ASSESSMENT)
    assert not report["task_accepted"] and not report["conclusion_valid"]
    assert any(row["kind"] == ("invalid_measurement" if failure == "ambiguous_measurement" else "refinement")
               for row in report["failures"])


def test_fine_grid_must_actually_increase_native_samples(planned, monkeypatch):
    read = robustness._plot
    coarse = {}

    def unchanged_grid(root, study, case, output):
        plot = read(root, study, case, output)
        if case.resolution == "coarse":
            coarse[case.scenario] = plot
        return coarse[case.scenario]

    monkeypatch.setattr(robustness, "_plot", unchanged_grid)
    with pytest.raises(EvidenceError, match="not accepted"):
        run_analysis(planned)
    report = load(planned, ASSESSMENT)
    assert report["coverage"]["complete"] and not report["conclusion_valid"]
    assert any(row["kind"] == "sample_count" for row in report["failures"])


@pytest.mark.parametrize("field", ["wave.raw", "inputs/design/parameters.inc"])
def test_matching_modified_copies_cannot_replace_native_agreement(work, field):
    result = load(work, RESULTS)
    source = f"analog/results/native/nominal_frequency_coarse/{field}"
    target = result["outputs"][source]
    original = (work / source).read_bytes()
    changed = original.replace(b"e-01", b"e-02", 1) if field == "wave.raw" else original.replace(b"resistance=1000", b"resistance=1100")
    assert changed != original
    (work / source).write_bytes(changed)
    (work / target).write_bytes(changed)
    with pytest.raises(EvidenceError, match="independent replay|generated circuit differs"):
        validate_simulation(work)


@pytest.mark.parametrize("field", ["inputs", "outputs", "runs", "cases"])
def test_missing_or_repeated_coverage_is_rejected(work, field):
    result = load(work, RESULTS)
    if isinstance(result[field], dict):
        result[field].pop(next(iter(result[field])))
    else:
        result[field].pop()
    save(work, RESULTS, result)
    assert stages.stage_completion_issues("simulation", work)


@pytest.mark.parametrize("bound", ["MAX_STUDY_SECONDS", "MAX_STUDY_OUTPUT_BYTES"])
def test_native_resource_failure_retains_diagnostics(planned, monkeypatch, bound):
    monkeypatch.setattr(robustness, bound, 0 if bound.endswith("SECONDS") else 1)
    with pytest.raises(EvidenceError, match="budget|exceeded"):
        run_analysis(planned)
    result, assessment = load(planned, RESULTS), load(planned, ASSESSMENT)
    assert result["status"] == "failed" and not result["execution_complete"]
    assert not assessment["task_accepted"]
    assert (planned / "analog/results/native").is_dir()


def test_original_results_are_never_overwritten(work):
    before = (work / RESULTS).read_bytes()
    with pytest.raises(FileExistsError):
        run_analysis(work)
    assert (work / RESULTS).read_bytes() == before


@pytest.mark.parametrize("failure", ["headroom", "refinement"])
def test_nonfinite_derived_arithmetic_is_not_an_accepted_diagnosis(planned, monkeypatch, failure):
    spec = load(planned, "design/operating.json")
    if failure == "headroom":
        spec["analyses"][0]["checks"][0].update(minimum=1e307, maximum=1.7e308)
        save(planned, "design/operating.json", spec)

    def extreme(plot, check):
        value = -1.7e308 if failure == "headroom" else (9e307 if len(plot.rows) < 500 else -9e307)
        return value, check["unit"]

    monkeypatch.setattr(robustness, "measure", extreme)
    with pytest.raises(EvidenceError, match="overflowed"):
        run_analysis(planned)
    report = load(planned, ASSESSMENT)
    assert not report["conclusion_valid"] and not report["task_accepted"]
    assert "Infinity" not in (planned / ASSESSMENT).read_text()


def test_oversized_original_source_is_rejected_before_text_parsing(planned, monkeypatch):
    import argus_verticals.analog_mixed_signal.study as study

    monkeypatch.setattr(study, "MAX_INPUT_BYTES", 1)
    with pytest.raises(EvidenceError, match="original inputs exceed"):
        resolve_study(planned)


def test_invalid_source_encoding_is_reported_by_stage(planned):
    (planned / "design/parameters.inc").write_bytes(b"\xff")
    assert stages.stage_completion_issues("model", planned)
