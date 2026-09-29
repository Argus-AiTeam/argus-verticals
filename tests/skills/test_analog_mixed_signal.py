from __future__ import annotations

import cmath
import json
import math
import shutil
import subprocess
from itertools import combinations
from pathlib import Path

import pytest
from argus.skills.stage_machine import StageCompletionError, complete_final_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.analog_mixed_signal import stages
from argus_verticals.analog_mixed_signal.evidence import (
    INPUTS_DIR,
    PLAN,
    RESULTS,
    RESULTS_DIR,
    EvidenceError,
    deck_inputs,
    validate_model,
    validate_plan,
    validate_simulation,
    validate_specification,
)
from argus_verticals.analog_mixed_signal.raw import Plot, measure, read_plot
from argus_verticals.analog_mixed_signal.run_analysis import run_analysis
from argus_verticals.analog_mixed_signal.run_reference import prepare_reference, run_reference


def save(root, relative, value):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def load(root, relative):
    return json.loads((root / relative).read_text(encoding="utf-8"))


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if shutil.which("ngspice") is None:
        pytest.skip("ngspice is required for native circuit analysis")
    root = tmp_path_factory.mktemp("analog") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    return Path(shutil.copytree(reference, tmp_path / "work"))


def test_native_reference_matches_independent_circuit_equations(reference, tmp_path):
    values = validate_simulation(reference)
    cutoff = 1 / (2 * math.pi * 1000 * 100e-9)
    gain = 100000 / (1 + 100000 / 11)
    assert values["rc_op"]["bias"] == pytest.approx(1)
    assert values["rc_dc"]["midpoint"] == pytest.approx(0.5)
    assert values["rc_ac"]["cutoff"] == pytest.approx(cutoff, rel=0.003)
    assert values["rc_ac"]["phase"] == pytest.approx(-45, abs=0.1)
    assert values["rc_tran"]["time_constant"] == pytest.approx(1e-4, rel=0.01)
    assert values["amplifier_op"]["bias"] == pytest.approx(gain * 0.1, rel=0.001)
    assert values["amplifier_ac"]["gain"] == pytest.approx(gain, rel=0.003)
    assert values["amplifier_ac"]["bandwidth"] == pytest.approx(10 * (1 + 100000 / 11), rel=0.003)
    result = load(reference, RESULTS)
    assert len(result["runs"]) == 6
    assert all(row["exit_code"] == 0 for row in result["runs"])
    assert all(row["cwd"] == INPUTS_DIR for row in result["runs"])
    assert len(result["outputs"]) == 18
    state = tmp_path / "state"
    persist_vertical(state, "analog_mixed_signal", workflow_profile="simulation")
    complete_final_stage(state, reason="independently checked model-level results", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "analog_mixed_signal")["ok"]
    assert load_vertical_contract("analog_mixed_signal", state).stage_order == ("simulation",)
    assert not (reference / "analog/REVIEW.md").exists()


@pytest.mark.parametrize("kind", ["op", "dc", "ac", "tran"])
def test_each_native_analysis_can_be_selected_alone(planned, reference, kind):
    plan = load(planned, PLAN)
    run = next(row for row in plan["runs"] if row["kind"] == kind)
    plan["runs"] = [run]
    plan["requirements"] = {
        key: value for key, value in plan["requirements"].items()
        if key in {check["requirement"] for check in run["checks"]}
    }
    save(planned, PLAN, plan)
    assert set(run_analysis(planned)) == {run["id"]}
    assert len(load(planned, RESULTS)["runs"]) == 1


def test_specification_and_model_do_not_require_simulation(planned, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    plan = load(planned, PLAN)
    plan.pop("runs")
    save(planned, PLAN, plan)
    assert validate_model(planned) == plan
    assert not stages.stage_completion_issues("model", planned)
    plan.pop("models")
    save(planned, PLAN, plan)
    assert validate_specification(planned) == plan
    assert not stages.stage_completion_issues("specification", planned)
    assert stages.stage_completion_issues("simulation", planned)
    assert not (planned / RESULTS_DIR).exists()


def test_all_custom_scopes_add_only_their_declared_obligations():
    from argus.core.vertical_contract import vertical_contract

    contract = vertical_contract("analog_mixed_signal", stages)
    assert stages.VERTICAL_SKILL_PARENTS == ()
    for count in range(1, len(stages.STAGE_ORDER) + 1):
        for requested in combinations(stages.STAGE_ORDER, count):
            expected = set(requested)
            if "review" in expected:
                expected.add("simulation")
            assert contract.compose_workflow(requested).stage_order == tuple(
                stage for stage in stages.STAGE_ORDER if stage in expected
            )


def test_missing_native_evidence_cannot_complete(tmp_path):
    persist_vertical(tmp_path, "analog_mixed_signal", workflow_profile="simulation")
    with pytest.raises(StageCompletionError):
        complete_final_stage(tmp_path, reason="no execution")


@pytest.mark.parametrize("location", ["model", "kind", "component", "unit", "statistic", "direction"])
@pytest.mark.parametrize("invalid", [None, [], {}, 12, True])
def test_json_enum_types_are_reported_as_evidence_errors(planned, location, invalid):
    plan = load(planned, PLAN)
    if location == "model":
        next(iter(plan["models"].values()))["kind"] = invalid
    elif location == "kind":
        plan["runs"][0]["kind"] = invalid
    else:
        plan["runs"][2]["checks"][0][location] = invalid
    save(planned, PLAN, plan)
    with pytest.raises(EvidenceError):
        validate_plan(planned)
    assert stages.stage_completion_issues("simulation", planned)


@pytest.mark.parametrize("invalid", [True, "1k", None, float("nan"), float("inf"), 10**500])
def test_nonfinite_or_nonnumeric_bounds_are_rejected(planned, invalid):
    plan = load(planned, PLAN)
    plan["runs"][0]["checks"][0]["maximum"] = invalid
    save(planned, PLAN, plan)
    with pytest.raises(EvidenceError, match="finite number"):
        validate_plan(planned)


@pytest.mark.parametrize("mutation", [
    "missing_plan", "missing_model", "changed_model", "changed_deck", "changed_plan",
    "missing_input_copy", "hardlinked_input", "self_copy", "outside_copy",
    "missing_run", "duplicate_run", "extra_run", "wrong_command", "wrong_cwd",
    "wrong_environment", "wrong_raw_path", "bad_exit", "boolean_exit", "empty_version",
    "native_error", "console_error", "console_encoding", "wrong_row_count", "truncated_raw",
    "missing_retained_copy", "changed_retained_copy", "hardlinked_output",
])
def test_native_evidence_rejects_missing_stale_or_contradictory_records(work, tmp_path, mutation):
    result = load(work, RESULTS)
    row = result["runs"][0]
    source = "models/rc.inc"
    if mutation == "missing_plan":
        (work / PLAN).unlink()
    elif mutation == "missing_model":
        (work / source).unlink()
    elif mutation in {"changed_model", "changed_deck", "changed_plan"}:
        relative = {"changed_model": source, "changed_deck": "benches/rc_op.cir", "changed_plan": PLAN}[mutation]
        with (work / relative).open("a") as stream:
            stream.write("\n" if relative == PLAN else "\n* Changed input\n")
    elif mutation == "missing_input_copy":
        (work / result["inputs"][source]).unlink()
    elif mutation == "hardlinked_input":
        target = work / result["inputs"][source]
        target.unlink()
        target.hardlink_to(work / source)
    elif mutation == "self_copy":
        result["inputs"][source] = source
    elif mutation == "outside_copy":
        shutil.copyfile(work / source, tmp_path / "outside.inc")
        result["inputs"][source] = "../outside.inc"
    elif mutation == "missing_run":
        result["runs"].pop()
    elif mutation == "duplicate_run":
        result["runs"].append(dict(row))
    elif mutation == "extra_run":
        result["runs"].append({**row, "id": "unrequested"})
    elif mutation == "wrong_command":
        row["command"].remove("-n")
    elif mutation == "wrong_cwd":
        row["cwd"] = "."
    elif mutation == "wrong_environment":
        result["environment"] = {}
    elif mutation == "wrong_raw_path":
        row["raw"] = "somewhere.raw"
    elif mutation in {"bad_exit", "boolean_exit"}:
        row["exit_code"] = 2 if mutation == "bad_exit" else True
    elif mutation == "empty_version":
        result["tool_version"] = ""
    elif mutation == "console_encoding":
        (work / row["console"]).write_bytes(b"\xffinvalid UTF-8")
    elif mutation in {"native_error", "console_error"}:
        with (work / row["log" if mutation == "native_error" else "console"]).open("a") as stream:
            stream.write("\nError: native analysis failed\n")
    elif mutation == "wrong_row_count":
        path = work / row["log"]
        path.write_text(path.read_text().replace("No. of Data Rows : 1", "No. of Data Rows : 2"))
    elif mutation == "truncated_raw":
        path = work / row["raw"]
        path.write_text(path.read_text()[:80])
    elif mutation == "missing_retained_copy":
        (work / result["outputs"][row["raw"]]).unlink()
    elif mutation == "changed_retained_copy":
        (work / result["outputs"][row["raw"]]).write_text("Not the saved waveform\n")
    elif mutation == "hardlinked_output":
        path = work / result["outputs"][row["raw"]]
        path.unlink()
        path.hardlink_to(work / row["raw"])
    save(work, RESULTS, result)
    expected_error = {
        "native_error": "native simulator output contains a failure",
        "console_error": "native simulator output contains a failure",
        "console_encoding": "cannot read native console",
        "wrong_row_count": "point counts disagree",
        "truncated_raw": "invalid native ngspice output",
    }.get(mutation)
    with pytest.raises(EvidenceError, match=expected_error):
        validate_simulation(work)


@pytest.mark.parametrize("directive", [
    ".control", ".lib external.lib typical", ".hdl model.va", ".osdi model.so",
    ".noise v(out) vin dec 10 1 1e6", ".pz v(out) 0 v(in) 0 vol pz",
    ".include ../outside.inc", ".include /tmp/outside.inc",
    'a1 %v(in) %v(out) filesource\n.model filesource filesource(file="wave.txt")',
])
def test_unsupported_or_external_spice_dependencies_are_rejected(planned, directive):
    deck = planned / "benches/rc_op.cir"
    deck.write_text(deck.read_text().replace(".end", directive + "\n.end"))
    with pytest.raises(EvidenceError):
        validate_plan(planned)


def test_include_closure_counts_analysis_and_rejects_cycles(planned):
    files, analyses = deck_inputs(planned, "benches/rc_ac.cir")
    assert files == {"benches/rc_ac.cir", "models/rc.inc"}
    assert analyses == ["ac"]
    model = planned / "models/rc.inc"
    original = model.read_text()
    model.write_text(original + '\n.include "models/rc.inc"\n')
    with pytest.raises(EvidenceError, match="cyclic"):
        validate_plan(planned)
    model.write_text(original + "\n.op\n")
    with pytest.raises(EvidenceError, match="exactly"):
        validate_plan(planned)
    model.write_text(original + "\n.end\n")
    with pytest.raises(EvidenceError, match="terminate"):
        validate_plan(planned)


def test_undeclared_model_and_uncovered_requirement_are_rejected(planned):
    plan = load(planned, PLAN)
    model = plan["models"].pop("models/rc.inc")
    save(planned, PLAN, plan)
    with pytest.raises(EvidenceError, match="provenance"):
        validate_plan(planned)
    plan["models"]["models/rc.inc"] = model
    plan["requirements"]["unmeasured"] = "An extra claim without any comparison"
    save(planned, PLAN, plan)
    with pytest.raises(EvidenceError, match="every declared requirement"):
        validate_plan(planned)


def test_changed_capacitance_fails_native_measurements_not_just_copy_checks(planned, reference):
    model = planned / "models/rc.inc"
    assert "100n" in model.read_text()
    model.write_text(model.read_text().replace("100n", "200n"))
    with pytest.raises(EvidenceError, match="rc_ac/cutoff.*outside"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert len(result["runs"]) == 6
    assert all(row["exit_code"] == 0 for row in result["runs"])
    assert (planned / result["inputs"]["models/rc.inc"]).read_bytes() == model.read_bytes()


def test_existing_results_are_not_overwritten(work):
    before = (work / RESULTS).read_bytes()
    with pytest.raises(FileExistsError):
        run_analysis(work)
    assert (work / RESULTS).read_bytes() == before
    assert validate_simulation(work)


def test_missing_tool_does_not_create_success_shaped_output(planned, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="ngspice is required"):
        run_analysis(planned)
    assert not (planned / RESULTS_DIR).exists()


@pytest.mark.parametrize("failure", ["timeout", "nonzero"])
def test_failed_process_preserves_partial_records_without_claiming_success(planned, monkeypatch, failure):
    monkeypatch.setattr(shutil, "which", lambda _: "/fixture/ngspice")

    def execute(command, **kwargs):
        if command == ["ngspice", "--version"]:
            return subprocess.CompletedProcess(command, 0, "ngspice test fixture\n", "")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, 120)
        return subprocess.CompletedProcess(command, 3, "", "synthetic failed process")

    monkeypatch.setattr(subprocess, "run", execute)
    with pytest.raises(RuntimeError, match="timed out|exited 3"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert len(result["runs"]) == 1
    assert result["runs"][0]["exit_code"] == (None if failure == "timeout" else 3)
    assert result["outputs"] == {}
    assert stages.stage_completion_issues("simulation", planned)


def test_review_requires_current_simulations_and_a_conclusion(work):
    assert stages.stage_completion_issues("review", work)
    (work / "analog/REVIEW.md").write_text("Only the stated ideal and behavioral models were checked.\n")
    assert not stages.stage_completion_issues("review", work)
    (work / "models/rc.inc").write_text("* Changed model\n")
    assert stages.stage_completion_issues("review", work)


def raw_text(kind="dc", rows=((0, 0), (1, 1)), *, imaginary_scale="0"):
    # Synthetic native-format fixture for the reader, not simulator evidence.
    plots = {"dc": "DC transfer characteristic", "tran": "Transient Analysis", "ac": "AC Analysis"}
    quantity = {"dc": "voltage", "tran": "time", "ac": "frequency"}[kind]
    lines = [
        "Title: reader fixture", f"Plotname: {plots[kind]}", f"Flags: {'complex' if kind == 'ac' else 'real'}",
        "No. Variables: 2", f"No. Points: {len(rows)}", "Variables:",
        f"\t0 axis {quantity}", "\t1 v(out) voltage", "Values:",
    ]
    for index, (axis, signal) in enumerate(rows):
        suffix = "," + imaginary_scale if kind == "ac" else ""
        value = f"{complex(signal).real},{complex(signal).imag}" if kind == "ac" else str(signal)
        lines.extend([f"{index}\t{axis}{suffix}", f"\t{value}"])
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("mutation", ["truncate", "extra_plot", "nan", "duplicate_axis", "wrong_plot", "wrong_flags", "wrong_index", "duplicate_vector", "too_many_points"])
def test_raw_parser_rejects_invalid_native_data(tmp_path, mutation):
    text = raw_text()
    if mutation == "truncate":
        text = text[:-4]
    elif mutation == "extra_plot":
        text += raw_text()
    elif mutation == "nan":
        text = text.replace("\t1\n", "\tnan\n")
    elif mutation == "duplicate_axis":
        text = raw_text(rows=((0, 0), (0, 1)))
    elif mutation == "wrong_plot":
        text = text.replace("DC transfer characteristic", "Operating Point")
    elif mutation == "wrong_flags":
        text = text.replace("Flags: real", "Flags: complex")
    elif mutation == "wrong_index":
        text = text.replace("1\t1", "5\t1")
    elif mutation == "duplicate_vector":
        text = text.replace("1 v(out)", "1 axis")
    elif mutation == "too_many_points":
        text = text.replace("No. Points: 2", "No. Points: 100001")
    path = tmp_path / "wave.raw"
    path.write_text(text)
    with pytest.raises(EvidenceError):
        read_plot(path, "dc")


def test_raw_missing_file_has_the_same_explicit_error_type(tmp_path):
    with pytest.raises(EvidenceError, match="invalid native"):
        read_plot(tmp_path / "missing.raw", "ac")


@pytest.mark.parametrize("unused_slot", ["5.14e-310", "nan", "inf"])
def test_ac_frequency_unused_imaginary_slot_is_not_a_signal(tmp_path, unused_slot):
    path = tmp_path / "wave.raw"
    path.write_text(raw_text("ac", rows=((1, 1), (2, 0.5 - 0.5j)), imaginary_scale=unused_slot))
    plot = read_plot(path, "ac")
    assert [row[0] for row in plot.rows] == [1 + 0j, 2 + 0j]
    assert plot.rows[1][1] == 0.5 - 0.5j


def test_descending_dc_is_normalized_without_changing_signal_association(tmp_path):
    path = tmp_path / "wave.raw"
    path.write_text(raw_text(rows=((2, 4), (1, 2), (0, 0))))
    plot = read_plot(path, "dc")
    assert measure(plot, {"vector": "v(out)", "component": "real", "statistic": "at", "at": 0.5}) == (1, "V")


def test_interpolation_windows_units_and_crossings():
    plot = Plot("tran", (("time", "time"), ("v(out)", "voltage"), ("i(vin)", "current")),
                ((0j, 0j, 2 + 0j), (1 + 0j, 2 + 0j, 2 + 0j), (2 + 0j, 0j, 2 + 0j)))
    check = {"vector": "v(out)", "component": "real", "statistic": "at", "at": 0.25}
    assert measure(plot, check) == (0.5, "V")
    assert measure(plot, {**check, "denominator": "i(vin)"}) == (0.25, "ohm")
    assert measure(plot, {**check, "statistic": "max", "window": [0.5, 1.5]}) == (2, "V")
    assert measure(plot, {**check, "statistic": "min", "window": [0.5, 1.5]}) == (1, "V")
    crossing = {**check, "statistic": "crossing", "window": [0, 2], "level": 1, "direction": "rising"}
    assert measure(plot, crossing) == (0.5, "s")
    assert measure(plot, {**crossing, "direction": "falling"}) == (1.5, "s")
    for invalid in ({**check, "at": 3}, {**crossing, "window": [-1, 2]}, {**crossing, "level": 3}):
        with pytest.raises(EvidenceError):
            measure(plot, invalid)


def test_crossing_at_a_sample_is_counted_once_and_ambiguous_crossings_fail():
    variables = (("time", "time"), ("v(out)", "voltage"))
    check = {"vector": "v(out)", "component": "real", "statistic": "crossing",
             "window": [0, 2], "level": 1, "direction": "rising"}
    plot = Plot("tran", variables, ((0j, 0j), (1 + 0j, 1 + 0j), (2 + 0j, 2 + 0j)))
    assert measure(plot, check) == (1, "s")
    plateau = Plot("tran", variables, ((0j, 0j), (1 + 0j, 1 + 0j), (2 + 0j, 1 + 0j)))
    with pytest.raises(EvidenceError, match="plateau"):
        measure(plateau, check)
    ringing = Plot("tran", variables, tuple((complex(x), complex(y)) for x, y in enumerate([0, 2, 0, 2])))
    with pytest.raises(EvidenceError, match="found 2"):
        measure(ringing, {**check, "window": [0, 3]})
    tangent = Plot("tran", variables, ((0j, 0j), (1 + 0j, 1 + 0j), (2 + 0j, 0j)))
    with pytest.raises(EvidenceError, match="found 0"):
        measure(tangent, check)


def test_phase_is_unwrapped_across_many_turns():
    degrees = [170 + 20 * index for index in range(1000)]
    plot = Plot("ac", (("frequency", "frequency"), ("v(out)", "voltage")),
                tuple((complex(index + 1), cmath.rect(1, math.radians(phase))) for index, phase in enumerate(degrees)))
    value, unit = measure(plot, {"vector": "v(out)", "component": "phase_deg", "statistic": "at", "at": 1000})
    assert unit == "deg"
    assert value == pytest.approx(degrees[-1])


def test_zero_denominators_undefined_phase_and_computed_overflow_fail():
    plot = Plot("op", (("v(out)", "voltage"), ("v(in)", "voltage")), ((0j, 0j),))
    check = {"vector": "v(out)", "component": "real", "statistic": "point"}
    with pytest.raises(EvidenceError, match="zero denominator"):
        measure(plot, {**check, "denominator": "v(in)"})
    with pytest.raises(EvidenceError, match="undefined"):
        measure(plot, {**check, "component": "phase_deg"})
    overflow = Plot("op", plot.variables, ((complex(1, 1e308), complex(1e-308)),))
    with pytest.raises(EvidenceError, match="nonfinite"):
        measure(overflow, {**check, "denominator": "v(in)", "component": "phase_deg"})


@pytest.mark.parametrize("role,operation", [
    ("manager", "stage_decision"), ("planner", "plan_preview"),
    ("engineer", "mission"), ("reviewer", "evaluate"),
])
@pytest.mark.parametrize("stage", stages.STAGE_ORDER)
def test_role_fragments_share_the_exact_contract_and_store_safe_commands(tmp_path, role, operation, stage):
    from argus.roles.prompts import ChecklistMode, RoleName, RolePromptRequest, resolve_role_prompt

    persist_vertical(tmp_path, "analog_mixed_signal", workflow_profile=stage)
    prompt = resolve_role_prompt(RolePromptRequest(
        role=RoleName(role), operation=operation, project_root=tmp_path,
        stage=stage, checklist_mode=ChecklistMode.STAGE,
    ))
    contract = Path(stages.__file__).with_name("evidence-contract.md").read_text()
    assert contract in prompt.role_banner
    assert stages.evidence_check_command("analog_mixed_signal", stage) in prompt.role_banner
    if stage in {"simulation", "review"}:
        assert "from argus_verticals.analog_mixed_signal.run_analysis import run_analysis" in prompt.role_banner
        assert "load_vertical_contract" in prompt.role_banner
    assert "Never manufacture" in prompt.role_banner


def test_production_role_requests_preserve_stage_and_separate_execution_state(tmp_path):
    from argus.roles.prompts import resolve_role_prompt
    from argus.roles.prompts.engineer import mission_request
    from argus.roles.prompts.manager import stage_decision_request
    from argus.roles.prompts.planner import PLAN_PREVIEW, continuous_request
    from argus.roles.prompts.reviewer import evaluate_request
    from argus.skills.stage_machine import current_stage

    state = tmp_path / "state"
    project = tmp_path / "circuit"
    project.mkdir()
    persist_vertical(state, "analog_mixed_signal", workflow_profile="simulation")
    requests = [
        stage_decision_request(state, stage="simulation"),
        continuous_request(state, operation=PLAN_PREVIEW, altitude_root=project, include_search_altitude=False),
        mission_request(state, altitude_root=project, stage=current_stage(state)),
        evaluate_request(state, altitude_root=project),
    ]
    canonical = Path(stages.__file__).with_name("evidence-contract.md").read_text()
    for request in requests:
        prompt = resolve_role_prompt(request)
        assert prompt.stage_order == ("simulation",)
        assert "## Analog work: simulation" in prompt.role_banner
        assert canonical in prompt.role_banner


@pytest.mark.parametrize("mutation,reason", [
    ("wrong_unit", "measured Hz, not declared V"),
    ("wrong_bounds", "outside"),
    ("missing_vector", "does not contain vector"),
    ("out_of_range", "outside the saved axis"),
])
def test_measurement_acceptance_is_recomputed_from_native_outputs(work, mutation, reason):
    plan = load(work, PLAN)
    check = plan["runs"][2]["checks"][0]
    if mutation == "wrong_unit":
        check["unit"] = "V"
    elif mutation == "wrong_bounds":
        check["minimum"], check["maximum"] = 10, 20
    elif mutation == "missing_vector":
        check["vector"] = "v(not_saved)"
    else:
        check["window"] = [0, 1e12]
    save(work, PLAN, plan)
    # Isolate the numeric/units checks from copy freshness in this parser test.
    shutil.copyfile(work / PLAN, work / load(work, RESULTS)["inputs"][PLAN])
    with pytest.raises(EvidenceError, match=reason):
        validate_simulation(work)
