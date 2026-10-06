from __future__ import annotations

import copy
import hashlib
import itertools
import json
import shutil
from pathlib import Path

import pytest
from argus.skills.stage_machine import complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.power_electronics import native, robustness, stages
from argus_verticals.power_electronics.evidence import validate_simulation
from argus_verticals.power_electronics.model import PLAN, RESULTS
from argus_verticals.power_electronics.robustness import ASSESSMENT, inspect_study
from argus_verticals.power_electronics.run_analysis import run_analysis
from argus_verticals.power_electronics.run_robustness_reference import (
    prepare_reference,
    run_reference,
)
from argus_verticals.power_electronics.study import resolve_study

SPEC = "design/operating.json"


def load(root, relative=SPEC):
    return json.loads((root / relative).read_text())


def save(root, value, relative=SPEC):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture(scope="module")
def native_references(tmp_path_factory):
    if shutil.which("ngspice") is None:
        pytest.skip("native ngspice is required")
    directory = tmp_path_factory.mktemp("power-robustness")
    roots = {}
    for name, goal, tight in [("design", "design", False), ("diagnose", "diagnose", True), ("failed", "design", True)]:
        root = directory / name
        if name == "failed":
            with pytest.raises(EvidenceError, match="task not accepted"):
                run_reference(root, goal=goal, tight=tight)
        else:
            run_reference(root, goal=goal, tight=tight)
        roots[name] = root
    return roots


@pytest.fixture
def work(native_references, tmp_path):
    original = native_references["design"]
    root = Path(shutil.copytree(original, tmp_path / "work"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(original), str(root)))
    return root


def test_cartesian_product_and_common_design(planned):
    spec = load(planned)
    spec["axes"].extend([
        {"id": "temperature", "target": "model.temperature_c", "unit": "degC", "source": "Declared temperatures.", "values": [0, 60]},
        {"id": "load", "target": "run.load_resistance_ohm", "unit": "ohm", "source": "Declared loads.", "values": [4.5, 5.5]},
    ])
    save(planned, spec)
    study = resolve_study(planned)
    assert study.grid_size == 16 and len(study.scenarios) == 17 and len(study.runs) == 34
    assert {tuple(s.coordinates.values()) for s in study.scenarios[1:]} == set(
        itertools.product([11.8, 12.2], [22e-6 * 0.8, 22e-6 * 1.2], [0, 60], [4.5, 5.5]),
    )
    assert {r["duty_cycle"] for _, r in study.runs} == {0.5304}
    for scenario in study.scenarios:
        coarse, fine = scenario.runs
        assert fine["max_step_s"] == coarse["max_step_s"] / 2
        assert {k: v for k, v in fine.items() if k not in ("id", "max_step_s")} == {
            k: v for k, v in coarse.items() if k not in ("id", "max_step_s")
        }
        assert coarse["checks"] == [{k: v for k, v in c.items() if not k.startswith("margin_")} for c in spec["checks"]]


def test_nominal_grid_deduplication_and_selected_tolerance(planned):
    spec = load(planned)
    spec["axes"][0]["values"] = [12, 12.2]
    spec["axes"][1]["factors"] = [1, 1.2]
    spec["design_variables"]["cap"] = {
        "target": "model.capacitance_f", "unit": "F", "source": "Allowed capacitor values.", "values": [22e-6, 33e-6],
    }
    plan = load(planned, PLAN)
    plan["robustness"]["design"]["cap"] = 33e-6
    save(planned, plan, PLAN)
    save(planned, spec)
    study = resolve_study(planned)
    assert study.grid_size == 4 and len(study.scenarios) == 4
    assert study.scenarios[0].model["capacitance_f"] == 33e-6
    assert study.scenarios[-1].model["capacitance_f"] == 33e-6 * 1.2


@pytest.mark.parametrize("path,value", [
    (("goal",), None), (("goal",), []), (("goal",), "pass_anyway"),
    (("axes",), []), (("axes",), [None]),
    (("axes", 0, "target"), []), (("axes", 0, "target"), "model.topology"),
    (("axes", 0, "unit"), "mV"), (("axes", 0, "values"), [12]),
    (("axes", 0, "values"), [12, 12]), (("axes", 0, "values"), [12, True]),
    (("axes", 0, "values"), [12, {}]), (("axes", 0, "values"), [12, float("inf")]),
    (("axes", 0, "values"), [12, 10**1000]), (("axes", 0, "values"), [12, 49]),
    (("axes", 0, "source"), ""), (("axes", 1, "factors"), [0, 1]),
    (("axes", 1, "factors"), [-1, 1]), (("axes", 1, "factors"), [0.8, 1e308]),
    (("maximum_steps_s",), [2e-7, 1.1e-7]), (("maximum_steps_s",), [0, 0]),
    (("checks", 0, "margin_lower"), -0.1), (("checks", 0, "margin_upper"), True),
    (("checks", 0, "margin_upper"), 1), (("checks", 0, "metric"), []),
    (("checks", 0, "minimum"), 10), (("checks", 0, "maximum"), float("nan")),
    (("design_variables", "duty", "unit"), "percent"),
    (("design_variables", "duty", "minimum"), 0.54),
    (("conditions", "load_step"), []),
    (("convergence",), []), (("convergence", 0, "metric"), {}),
    (("convergence", 0, "max_delta"), -0.1),
    (("convergence", 0, "window"), "missing"),
])
def test_invalid_specification_is_explicit_in_all_scopes(planned, path, value):
    spec = load(planned)
    owner = spec
    for key in path[:-1]:
        owner = owner[key]
    owner[path[-1]] = value
    save(planned, spec)
    with pytest.raises(EvidenceError):
        resolve_study(planned)
    for stage in ("specification", "model", "simulation"):
        assert stages.stage_completion_issues(stage, planned)


@pytest.mark.parametrize("change", [
    "repeat_axis", "repeat_id", "repeat_design", "both_axis_kinds", "overwrite_design",
    "temperature_factor", "missing_load_step", "grid_limit", "missing_comparison",
    "repeat_comparison", "missing_choice", "extra_choice", "choice_bool", "choice_outside",
    "diagnose_variable", "legacy_runs", "legacy_convergence", "uncovered_requirement",
])
def test_no_silent_scope_or_design_changes(planned, change):
    spec, plan = load(planned), load(planned, PLAN)
    if change == "repeat_axis":
        spec["axes"].append({**spec["axes"][0], "id": "other"})
    elif change == "repeat_id":
        spec["axes"][1]["id"] = spec["axes"][0]["id"]
    elif change == "repeat_design":
        spec["design_variables"]["other"] = spec["design_variables"]["duty"]
        plan["robustness"]["design"]["other"] = 0.53
    elif change == "both_axis_kinds":
        spec["axes"][0]["factors"] = [0.9, 1.1]
    elif change == "overwrite_design":
        spec["axes"][0].update(target="run.duty_cycle", unit="1", values=[0.52, 0.54])
    elif change == "temperature_factor":
        spec["axes"][1]["target"] = "model.temperature_c"
    elif change == "missing_load_step":
        spec["axes"][0].update(target="run.load_step.resistance_ohm", unit="ohm")
    elif change == "grid_limit":
        spec["axes"][0]["values"] = list(range(8, 16))
        spec["axes"][1]["factors"] = [0.8, 1, 1.2]
    elif change == "missing_comparison":
        spec["convergence"].pop()
    elif change == "repeat_comparison":
        spec["convergence"].append(spec["convergence"][0])
    elif change == "missing_choice":
        plan["robustness"]["design"] = {}
    elif change == "extra_choice":
        plan["robustness"]["design"]["extra"] = 1
    elif change == "choice_bool":
        plan["robustness"]["design"]["duty"] = True
    elif change == "choice_outside":
        plan["robustness"]["design"]["duty"] = 0.55
    elif change == "diagnose_variable":
        spec["goal"] = "diagnose"
    elif change.startswith("legacy_"):
        plan[change.removeprefix("legacy_")] = []
    else:
        plan["requirements"]["missing"] = "Not covered."
    save(planned, spec)
    save(planned, plan, PLAN)
    with pytest.raises(EvidenceError):
        resolve_study(planned)


def test_point_budget_is_for_all_corners(planned, monkeypatch):
    from argus_verticals.power_electronics import study

    monkeypatch.setattr(study, "MAX_ESTIMATED_POINTS", 100_000)
    with pytest.raises(EvidenceError, match="aggregate point budget"):
        resolve_study(planned)


def test_native_design_pass_and_negative_diagnosis_have_distinct_meanings(native_references, tmp_path):
    from argus.engineer.round_evidence import RoundEvidenceRequest, collect_round_evidence

    for name, root in native_references.items():
        report = inspect_study(root)
        assert report["conclusion_valid"] and report["coverage"]["complete"]
        assert len(report["coverage"]["completed_runs"]) == 10
        assert all(c["passed"] for c in report["comparisons"])
        assert all(type(c["passed"]) is bool for c in report["checks"])
        assert report["status"] == ("passed" if name == "design" else "failed")
        assert report["task_accepted"] == (name != "failed")
        assert load(root, RESULTS)["status"] == ("failed" if name == "failed" else "complete")
        state = tmp_path / name
        persist_vertical(state, "power_electronics", workflow_profile="simulation")
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        gathered = collect_round_evidence(RoundEvidenceRequest(root, state / "handoffs/task", 1))
        host, = [item for item in gathered if item.provider.startswith("argus_verticals.hardware.shared.review:")]
        assert ('"issues": []' in host.reviewer_text) == (name != "failed")
        assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        if name == "failed":
            with pytest.raises(EvidenceError, match="task not accepted"):
                validate_simulation(root)
        else:
            complete_final_stage(state, reason="Complete finite native study", evidence_root=root)
            assert vertical_completion_certificate_status(state, "power_electronics")["ok"]
        if name != "design":
            nominal = [r for r in report["runs"] if r["scenario"] == "nominal"]
            assert all(5.971 <= r["measurements"]["settled"]["output_mean_v"] <= 6.029 for r in nominal)
            assert len(report["failures"]) == 8
            assert {f["scenario"] for f in report["failures"]} == {f"corner_{i:03d}" for i in range(4)}
        for check in report["checks"]:
            values = [(r["id"], r["measurements"][check["window"]][check["metric"]]) for r in report["runs"]]
            low = min(values, key=lambda p: p[1])
            high = max(values, key=lambda p: p[1])
            assert check["worst_observed_lower"]["run"] == low[0]
            assert check["worst_observed_lower"]["lower_headroom"] == low[1] - check["minimum"]
            assert check["worst_observed_upper"]["run"] == high[0]
            assert check["worst_observed_upper"]["upper_headroom"] == check["maximum"] - high[1]


@pytest.mark.parametrize("change", ["omitted", "reordered", "repeated", "scenario", "design", "goal", "copy", "command", "unfinished"])
def test_incomplete_or_altered_native_records_cannot_complete(work, change):
    result = load(work, RESULTS)
    if change == "omitted":
        result["runs"].pop()
    elif change == "reordered":
        result["runs"].reverse()
    elif change == "repeated":
        result["runs"][1] = result["runs"][0]
    elif change == "scenario":
        result["scenarios"].pop()
    elif change == "design":
        result["design"]["duty"] = 0.53
    elif change == "goal":
        result["goal"] = "diagnose"
    elif change == "copy":
        result["outputs"].pop(next(iter(result["outputs"])))
    elif change == "command":
        result["runs"][0]["execution"]["exit_code"] = False
    else:
        result["execution_complete"] = False
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError):
        inspect_study(work)


@pytest.mark.parametrize("relative", [SPEC, "design/buck.json", PLAN])
def test_all_source_bytes_are_bound(work, relative):
    path = work / relative
    path.write_text(path.read_text() + "\n")
    with pytest.raises(EvidenceError, match="changed file"):
        inspect_study(work)


def test_forged_assessment_is_recomputed(work):
    report = load(work, ASSESSMENT)
    report["checks"][0]["worst_observed_upper"]["upper_headroom"] += 1
    save(work, report, ASSESSMENT)
    with pytest.raises(EvidenceError, match="independently recomputed"):
        inspect_study(work)


def test_replay_detects_modified_native_samples_even_with_matching_copies(work):
    result = load(work, RESULTS)
    source = "power/results/native/nominal_coarse/wave.raw"
    data = (work / source).read_text()
    header, samples = data.split("Values:\n", 1)
    lines = samples.splitlines()
    lines[2] = " 1.0"
    modified = header + "Values:\n" + "\n".join(lines) + "\n"
    (work / source).write_text(modified)
    (work / result["outputs"][source]).write_text(modified)
    with pytest.raises(EvidenceError, match="independent replay"):
        inspect_study(work)


def test_inspection_is_read_only(work):
    def fingerprints():
        return {p.relative_to(work): hashlib.sha256(p.read_bytes()).digest() for p in work.rglob("*") if p.is_file()}

    before = fingerprints()
    inspect_study(work)
    assert before == fingerprints()
    with pytest.raises(FileExistsError):
        run_analysis(work)


@pytest.mark.parametrize("fault", ["measurement", "refinement", "samples", "margin", "zero"])
def test_aggregation_never_accepts_invalid_diagnosis(native_references, monkeypatch, fault):
    root = native_references["diagnose"]
    study = resolve_study(root)
    saved = load(root, ASSESSMENT)
    saved_values = {r["id"]: r["measurements"] for r in saved["runs"]}
    # These unit faults isolate aggregation; the references above execute and replay real ngspice.
    monkeypatch.setattr(robustness.native, "execute", lambda *a, **k: None)
    original = native.check_output
    plots = {}

    def output(path, model, run):
        if run["id"] not in plots:
            plots[run["id"]] = original(root / "power/results/native" / run["id"], model, run)
        if fault == "samples":
            return plots.setdefault("same", plots[run["id"]])
        return plots[run["id"]]

    def measure(plot, model, run):
        if fault == "measurement" and run["id"] == "nominal_fine":
            raise EvidenceError("Deliberate invalid physical measurement.")
        values = copy.deepcopy(saved_values[run["id"]])
        if fault == "refinement" and run["id"].endswith("_fine"):
            values["settled"]["output_mean_v"] += 0.02
        if fault in ("margin", "zero"):
            values["settled"]["output_mean_v"] = 6.03
        return values

    monkeypatch.setattr(robustness.native, "check_output", output)
    monkeypatch.setattr(robustness, "measurements", measure)
    if fault == "zero":
        study.specification["checks"][0]["margin_upper"] = 0
    report = robustness._collect(root, study)
    if fault in ("measurement", "refinement", "samples"):
        assert not report["task_accepted"] and not report["conclusion_valid"]
        assert report["coverage"]["complete"] == (fault != "measurement")
    else:
        voltage = report["checks"][0]
        assert voltage["worst_observed_upper"]["upper_headroom"] == 0
        assert voltage["passed"] == (fault == "zero")
        assert report["task_accepted"] and report["conclusion_valid"]
        assert report["status"] == ("passed" if fault == "zero" else "failed")


@pytest.mark.parametrize("budget", ["time", "output"])
def test_study_budget_failure_is_incomplete_not_a_diagnosis(planned, monkeypatch, budget):
    spec = load(planned)
    spec["goal"], spec["design_variables"] = "diagnose", {}
    plan = load(planned, PLAN)
    plan["robustness"]["design"] = {}
    save(planned, spec)
    save(planned, plan, PLAN)
    monkeypatch.setattr(robustness, "MAX_STUDY_SECONDS" if budget == "time" else "MAX_STUDY_OUTPUT_BYTES", 0 if budget == "time" else 1)
    with pytest.raises(EvidenceError, match="exceeded"):
        run_analysis(planned)
    report = load(planned, ASSESSMENT)
    assert report["status"] == "incomplete" and not report["task_accepted"]
    assert not report["coverage"]["complete"]
    assert load(planned, RESULTS)["status"] == "failed"
    with pytest.raises(EvidenceError):
        validate_simulation(planned)


@pytest.mark.parametrize("options", [{"timeout_seconds": 0}, {"maximum_output_bytes": 1}])
def test_per_call_native_budgets_preserve_failure(planned, tmp_path, options):
    study = resolve_study(planned)
    scenario, run = study.runs[0]
    output = tmp_path / "limited"
    with pytest.raises(EvidenceError, match="exceeded"):
        native.execute(scenario.model, run, output, **options)
    assert (output / "model.cir").is_file()


@pytest.mark.parametrize("options", [{"timeout_seconds": True}, {"timeout_seconds": -1}, {"maximum_output_bytes": False}, {"maximum_output_bytes": 1.5}])
def test_malformed_resource_limits_are_rejected(planned, tmp_path, options):
    scenario, run = resolve_study(planned).runs[0]
    with pytest.raises(EvidenceError):
        native.execute(scenario.model, run, tmp_path / "invalid", **options)
