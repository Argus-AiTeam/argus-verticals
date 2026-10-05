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
    deck_inputs,
    validate_plan,
    validate_simulation,
)
from argus_verticals.analog_mixed_signal.robustness import ASSESSMENT, inspect_study
from argus_verticals.analog_mixed_signal.run_analysis import run_analysis
from argus_verticals.analog_mixed_signal.run_robustness_reference import (
    diode_voltage,
    prepare_reference,
)
from argus_verticals.analog_mixed_signal.study import analysis_grid, resolve_study, spice_number
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
            assert summary["resolution_scope"] == ["coarse", "fine"]
            for side in ("lower", "upper"):
                worst = summary[f"worst_observed_{side}"]
                run = next(row for row in relevant if row["id"] == worst["run"])
                assert worst["resolution"] == run["resolution"]
                assert worst[f"{side}_margin_surplus"] == worst[f"{side}_headroom"] - check.get(f"margin_{side}", 0)
    assert expected_failures == {(row["run"], row["check"], row["kind"]) for row in report["failures"]}


def test_accepted_diagnosis_reuses_native_evidence_across_report_changes(work, tmp_path, monkeypatch):
    from argus.core.pipeline_state import read_pipeline_state
    from argus.engineer.round_evidence import RoundEvidenceRequest, collect_round_evidence

    state = tmp_path / "state"
    persist_vertical(state, "analog_mixed_signal", workflow_profile="simulation")
    selected = read_pipeline_state(state)
    calls = []
    execute = robustness._execute

    def counted(*args, **kwargs):
        calls.append(args[2].id)
        return execute(*args, **kwargs)

    monkeypatch.setattr(robustness, "_execute", counted)
    before = {p.relative_to(work): p.read_bytes() for p in work.rglob("*") if p.is_file()}
    gathered = collect_round_evidence(RoundEvidenceRequest(work, state / "handoffs/task", 1))
    host, = [item for item in gathered if item.provider.startswith("argus_verticals.hardware.shared.review:")]
    assert '"issues": []' in host.reviewer_text
    assert read_pipeline_state(state) == selected
    assert (state / "analog-validation/implementation/shared/native.py").is_file()
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


@pytest.mark.parametrize("literal,expected", [
    ("100n", 1e-7), ("10u", 1e-5), ("20u", 2e-5), ("0.1m", 1e-4),
    ("1e-3k", 1), ("2.5MEG", 2.5e6), ("-250p", -2.5e-10),
])
def test_spice_units_convert_once_without_double_rounding(literal, expected):
    assert spice_number(literal) == expected


def test_original_suffix_nominal_matches_specification_exactly(planned):
    path = planned / "design/parameters.inc"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(".param capacitance=100n" if line.startswith(".param capacitance=") else line
                              for line in lines) + "\n")
    assert resolve_study(planned).scenarios[0]["parameters"]["capacitance"] == 1e-7


def test_relative_sample_on_decimal_boundary_is_not_rejected_or_widened(planned):
    path = planned / "design/parameters.inc"
    path.write_text(path.read_text().replace(".param input_v=1\n", ".param input_v=0.1\n"))
    spec = load(planned, "design/operating.json")
    spec["parameters"]["input_v"].update(nominal=0.1, minimum=0.09, maximum=0.11)
    spec["axes"] = [{"id": "input", "parameter": "input_v", "unit": "1", "factors": [0.9, 1.1], "source": "original"}]
    save(planned, "design/operating.json", spec)
    assert [row["parameters"]["input_v"] for row in resolve_study(planned).scenarios] == [0.1, 0.09, 0.11]
    spec["axes"][0]["factors"][1] = math.nextafter(1.1, math.inf)
    save(planned, "design/operating.json", spec)
    with pytest.raises(EvidenceError, match="outside declared model validity"):
        resolve_study(planned)


def test_integer_factor_keeps_enough_precision_at_a_binary_midpoint(planned):
    path = planned / "design/parameters.inc"
    path.write_text(path.read_text().replace(".param input_v=1\n", ".param input_v=1e-60\n"))
    spec = load(planned, "design/operating.json")
    spec["parameters"]["input_v"].update(nominal=1e-60, minimum=0, maximum=1)
    # The exact product is just above the midpoint between 1 and its next binary64 value.
    factor = (2**53 + 1) * 5**53 * 10**7 + 1
    spec["axes"] = [{"id": "input", "parameter": "input_v", "unit": "1", "factors": [1, factor], "source": "original"}]
    save(planned, "design/operating.json", spec)
    with pytest.raises(EvidenceError, match="outside declared model validity"):
        resolve_study(planned)


def repeated_inputs(root, depth=8):
    plan = load(root, PLAN)
    for index in range(depth):
        relative = f"design/repeated_{index}.inc"
        content = "* " + "constant " * 100 + "\n" if index == depth-1 else f'.include "design/repeated_{index+1}.inc"\n' * 2
        (root / relative).write_text(content)
        plan["models"][relative] = dict(plan["models"]["design/circuit.inc"])
    path = root / "design/circuit.inc"
    path.write_text(path.read_text() + '.include "design/repeated_0.inc"\n')
    save(root, PLAN, plan)
    return plan


def test_repeated_includes_are_inspected_once_without_changing_analysis_multiplicity(planned, monkeypatch):
    plan = repeated_inputs(planned)
    read = Path.read_text
    reads = []

    def counted(path, *args, **kwargs):
        reads.append(path)
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted)
    paths, kinds = deck_inputs(planned, "benches/frequency.cir")
    assert kinds == ["ac"]
    assert set(paths) <= plan["models"].keys()
    assert len(reads) == len(set(reads)) == len(paths)
    monkeypatch.setattr(Path, "read_text", read)
    leaf = planned / "design/repeated_7.inc"
    leaf.write_text(".op\n")
    _, kinds = deck_inputs(planned, "benches/frequency.cir")
    assert kinds.count("op") == 128 and kinds.count("ac") == 1


def test_expanded_include_bytes_are_bounded_before_native_work(planned, monkeypatch):
    from argus_verticals.analog_mixed_signal import study

    plan = repeated_inputs(planned)
    original_bytes = sum((planned / name).stat().st_size for name in {PLAN, "design/operating.json", *plan["models"]})
    monkeypatch.setattr(study, "MAX_INPUT_BYTES", original_bytes + 1)
    with pytest.raises(EvidenceError, match="expanded SPICE inputs"):
        resolve_study(planned)
    assert not (planned / "analog/results").exists()


def test_undeclared_include_is_rejected_before_reading_it(planned, monkeypatch):
    hidden = planned / "design/undeclared.inc"
    hidden.write_text("* Not an original declared model\n")
    circuit = planned / "design/circuit.inc"
    circuit.write_text(circuit.read_text() + '.include "design/undeclared.inc"\n')
    read = Path.read_text

    def declared_only(path, *args, **kwargs):
        assert path != hidden, "undeclared input was read before its provenance was checked"
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", declared_only)
    with pytest.raises(EvidenceError, match="provenance"):
        resolve_study(planned)


def test_positive_headroom_can_still_fail_the_required_margin(planned):
    spec = load(planned, "design/operating.json")
    check = spec["analyses"][0]["checks"][0]
    check.update(minimum=0.7, maximum=0.84, margin_upper=0.04)
    save(planned, "design/operating.json", spec)
    report = run_analysis(planned)
    summary = next(row for row in report["checks"] if row["id"] == "gain")
    worst = summary["worst_observed_upper"]
    assert worst["within_limits"] and worst["upper_headroom"] > 0
    assert worst["upper_margin_surplus"] < 0 and not worst["required_margins_met"]
    assert not summary["passed"] and report["task_accepted"]
    assert any(row["kind"] == "margin" and row["resolution"] == worst["resolution"] for row in report["failures"])


def rlc_project(root, *, ambiguous=False):
    root.mkdir()
    (root / "analog").mkdir()
    (root / "parameters.inc").write_text(".param resistance=20\n.param inductance=10m\n.param capacitance=1u\n")
    (root / "circuit.inc").write_text(
        "Vin in 0 DC 1 AC 1\nRseries in damp {resistance}\n"
        "Lseries damp out {inductance} IC=0\nCshunt out 0 {capacitance} IC=0\n"
    )
    for name, directive in (("frequency", ".ac dec 400 10 100000"), ("step", ".tran 1u 5m 0 1u uic")):
        (root / f"{name}.cir").write_text(
            "Original underdamped RLC network\n.include parameters.inc\n.include circuit.inc\n"
            ".save v(in) v(out)\n" + directive + "\n.end\n"
        )
    spec = {
        "goal": "diagnose", "source": "Original ideal second-order low-pass circuit.",
        "limitations": ["Finite samples of ideal RLC, not physical qualification."],
        "parameter_file": "parameters.inc",
        "parameters": {
            "resistance": {"nominal": 20, "minimum": 10, "maximum": 40, "unit": "ohm", "source": "Original series damping."},
            "inductance": {"nominal": 0.01, "minimum": 0.005, "maximum": 0.02, "unit": "H", "source": "Original ideal inductor."},
            "capacitance": {"nominal": 1e-6, "minimum": 0.5e-6, "maximum": 2e-6, "unit": "F", "source": "Original ideal capacitor."},
        },
        "design_variables": {},
        "axes": [{"id": "r", "parameter": "resistance", "unit": "1", "factors": [0.9, 1.1], "source": "Original damping samples."}],
        "relative_tolerances": [1e-5, 1e-7],
        "analyses": [
            {"id": "frequency", "kind": "ac", "netlist": "frequency.cir", "checks": [{
                "id": "resonance", "requirement": "frequency", "vector": "v(out)", "denominator": "v(in)",
                "component": "magnitude", "statistic": "max", "window": [100, 10000],
                "unit": "1", "minimum": 1, "maximum": 4, "margin_upper": 0.1, "max_delta": 0.01,
            }]},
            {"id": "step", "kind": "tran", "netlist": "step.cir", "checks": [{
                "id": "overshoot", "requirement": "step", "vector": "v(out)",
                "component": "real", "statistic": "max", "window": [1e-8, 0.005],
                "unit": "V", "minimum": 0.9, "maximum": 1.2, "margin_upper": 0.01, "max_delta": 1e-4,
            }]},
        ],
    }
    if ambiguous:
        spec["analyses"][1]["checks"][0].update(
            statistic="crossing", direction="rising", level=1, unit="s",
            minimum=0, maximum=0.005, margin_upper=0, max_delta=1e-6,
        )
    (root / "operating.json").write_text(json.dumps(spec))
    plan = {
        "objective": "Diagnose damping, resonance and overshoot of the supplied second-order network.",
        "requirements": {"frequency": "Bound resonant gain.", "step": "Bound transient overshoot."},
        "limitations": spec["limitations"],
        "models": {
            name: {"kind": "testbench" if name.endswith(".cir") else "ideal", "source": spec["source"],
                   "validity": "Declared parameter ranges.", "limitations": spec["limitations"]}
            for name in ("parameters.inc", "circuit.inc", "frequency.cir", "step.cir")
        },
        "robustness": {"specification": "operating.json", "design": {}},
    }
    save(root, PLAN, plan)
    return root


def test_real_resonant_rlc_matches_second_order_equations(tmp_path):
    root = rlc_project(tmp_path / "rlc")
    report = run_analysis(root)
    assert report["conclusion_valid"] and report["task_accepted"] and report["status"] == "failed"
    assert len(report["runs"]) == 12 and len(report["comparisons"]) == 6
    assert all(row["passed"] for row in report["comparisons"])
    for row in report["runs"]:
        p = row["parameters"]
        damping = p["resistance"] / 2 * math.sqrt(p["capacitance"] / p["inductance"])
        if row["analysis"] == "frequency":
            expected = 1/(2*damping*math.sqrt(1-damping*damping))
            assert row["measurements"]["resonance"] == pytest.approx(expected, abs=0.01)
        else:
            expected = 1 + math.exp(-math.pi*damping/math.sqrt(1-damping*damping))
            assert row["measurements"]["overshoot"] == pytest.approx(expected, abs=1e-4)
    assert validate_simulation(root) == report


def test_real_ringing_does_not_turn_multiple_crossings_into_a_valid_diagnosis(tmp_path):
    root = rlc_project(tmp_path / "ambiguous-rlc", ambiguous=True)
    with pytest.raises(EvidenceError, match="not accepted"):
        run_analysis(root)
    report = load(root, ASSESSMENT)
    assert not report["conclusion_valid"] and not report["task_accepted"]
    failures = [row for row in report["failures"] if row["kind"] == "invalid_measurement"]
    assert len(failures) == 6 and all("expected one crossing" in row["reason"] for row in failures)


@pytest.mark.parametrize("role", ["engineer", "reviewer"])
def test_role_context_names_the_real_runtime_not_cli_scratch(planned, tmp_path, monkeypatch, role):
    runtime = tmp_path / "argus-task-state"
    monkeypatch.setenv("ARGUS_SKILL_SESSION_ROOT", str(runtime))
    prompt = stages.render_role_prompt_fragment(
        role=role, operation="mission", stage="simulation", scope="", project_root=planned,
    )
    assert f"Argus task runtime root: `{runtime}`" in prompt
    assert f"Installed analog provider source: `{Path(stages.__file__).resolve().parent}`" in prompt
    assert "without overriding `ARGUS_SKILL_SESSION_ROOT`" in prompt
    assert "not the native CLI's own session" in prompt
    assert not runtime.exists()


def test_standalone_role_context_does_not_invent_runtime_state(planned, monkeypatch):
    monkeypatch.delenv("ARGUS_SKILL_SESSION_ROOT", raising=False)
    prompt = stages.render_role_prompt_fragment(
        role="reviewer", operation="mission", stage="review", scope="", project_root=planned,
    )
    assert "No Argus task runtime root is configured" in prompt
    assert "standalone operating-envelope checks perform full native replay" in prompt
