from __future__ import annotations

import json
import math
import shutil
from itertools import combinations
from pathlib import Path

import numpy as np
import pytest
import skrf as rf
from argus.skills.stage_machine import StageCompletionError, complete_final_stage, current_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.rf_design import stages
from argus_verticals.rf_design.evidence import (
    PLAN,
    RESULTS,
    validate_analysis,
    validate_model,
    validate_plan,
)
from argus_verticals.rf_design.networks import (
    EvidenceError,
    build_networks,
    measure,
    read_touchstone,
    validate_network,
)
from argus_verticals.rf_design.run_analysis import run_analysis
from argus_verticals.rf_design.run_reference import prepare_reference, run_reference


def load(root, relative=PLAN):
    return json.loads((root / relative).read_text())


def save(root, value, relative=PLAN):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    root = tmp_path_factory.mktemp("rf") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    return Path(shutil.copytree(reference, tmp_path / "work"))


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


def test_six_actual_calculations_match_independent_equations(reference, tmp_path):
    values = validate_analysis(reference)
    assert values["attenuator"]["gain_db"] == pytest.approx(20 * math.log10(0.5), abs=1e-12)
    assert values["twice"]["gain_db"] == pytest.approx(20 * math.log10(0.25), abs=1e-12)
    assert values["resistor"]["reflection"] == pytest.approx(1 / 3, abs=1e-12)
    assert values["resistor"]["transmission"] == pytest.approx(2 / 3, abs=1e-12)
    assert values["resistor_75"]["reflection"] == pytest.approx(0.25, abs=1e-12)
    assert values["resistor_75"]["transmission"] == pytest.approx(0.75, abs=1e-12)
    assert values["quarter_wave"]["phase"] == pytest.approx(-90, abs=1e-12)
    assert values["match"]["input_match"] < 1e-12
    assert values["match"]["transmission"] == pytest.approx(1, abs=1e-12)
    assert values["match"]["phase"] == pytest.approx(-45, abs=1e-12)
    assert values["match"]["power_bound"] == pytest.approx(1, abs=1e-12)
    assert values["match"]["reciprocity"] < 1e-12
    result = load(reference, RESULTS)
    assert len(result["studies"]) == len(result["outputs"]) == 6
    assert result["versions"]["scikit-rf"] == rf.__version__
    state = tmp_path / "state"
    persist_vertical(state, "rf_design", workflow_profile="analysis")
    complete_final_stage(state, reason="independent network equations checked", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "rf_design")["ok"]
    assert not (reference / "rf/REVIEW.md").exists()


def test_only_selected_studies_and_dependencies_are_calculated(planned):
    plan = load(planned)
    plan["studies"] = [plan["studies"][1]]
    plan["requirements"] = {"twice": plan["requirements"]["twice"]}
    plan["networks"]["unselected"] = {"kind": "touchstone", "path": "missing-file.s2p"}
    save(planned, plan)
    _, networks, inputs = validate_plan(planned)
    assert set(networks) == {"attenuator", "twice"}
    assert inputs == ["data/attenuator.s2p", PLAN]
    assert set(run_analysis(planned)) == {"twice"}
    with pytest.raises(EvidenceError):
        validate_model(planned)


def test_all_custom_scopes_have_only_the_required_companions():
    contract = load_vertical_contract("rf_design")
    assert stages.VERTICAL_SKILL_PARENTS == ()
    for count in range(1, 5):
        for requested in combinations(stages.STAGE_ORDER, count):
            expected = set(requested)
            if "review" in requested:
                expected.add("analysis")
            assert contract.compose_workflow(requested).stage_order == tuple(
                stage for stage in stages.STAGE_ORDER if stage in expected
            )


def test_missing_results_never_certify(tmp_path):
    persist_vertical(tmp_path, "rf_design", workflow_profile="analysis")
    with pytest.raises(StageCompletionError):
        complete_final_stage(tmp_path, reason="no calculation")


def test_early_scopes_and_review_keep_distinct_requirements(planned, work):
    plan = load(planned)
    plan.pop("studies")
    save(planned, plan)
    assert not stages.stage_completion_issues("model", planned)
    plan.pop("networks")
    save(planned, plan)
    assert not stages.stage_completion_issues("specification", planned)
    assert stages.stage_completion_issues("analysis", planned)
    assert stages.stage_completion_issues("review", work)
    (work / "rf/REVIEW.md").write_text("Only the explicitly ideal sampled network models were checked.\n")
    assert not stages.stage_completion_issues("review", work)


@pytest.mark.parametrize("mutation", [
    "plan", "source", "missing_source", "missing_copy", "hardlink", "self_copy",
    "missing_study", "duplicate_study", "extra_study", "wrong_operation", "failed",
    "empty_version", "wrong_path", "wrong_network", "missing_export", "changed_export",
    "changed_retained", "hardlinked_output",
])
def test_records_reject_stale_or_inconsistent_evidence(work, mutation):
    result = load(work, RESULTS)
    row = result["studies"][0]
    if mutation in ("plan", "source"):
        relative = PLAN if mutation == "plan" else "data/attenuator.s2p"
        with (work / relative).open("a") as stream:
            stream.write("\n")
    elif mutation == "missing_source":
        (work / "data/attenuator.s2p").unlink()
    elif mutation == "missing_copy":
        (work / result["inputs"][PLAN]).unlink()
    elif mutation == "hardlink":
        path = work / result["inputs"][PLAN]
        path.unlink()
        path.hardlink_to(work / PLAN)
    elif mutation == "self_copy":
        result["inputs"][PLAN] = PLAN
    elif mutation == "missing_study":
        result["studies"].pop()
    elif mutation == "duplicate_study":
        result["studies"].append(dict(row))
    elif mutation == "extra_study":
        result["studies"].append({**row, "id": "extra"})
    elif mutation == "wrong_operation":
        result["operation"] = "fabricated"
    elif mutation == "failed":
        result["status"] = "failed"
    elif mutation == "empty_version":
        result["versions"]["scikit-rf"] = ""
    elif mutation == "wrong_path":
        row["path"] = "elsewhere.ts"
    elif mutation == "wrong_network":
        row["network"] = "twice"
    elif mutation == "missing_export":
        (work / row["path"]).unlink()
    elif mutation == "changed_export":
        (work / row["path"]).write_text("invalid network\n")
    elif mutation == "changed_retained":
        (work / result["outputs"][row["path"]]).write_text("changed\n")
    elif mutation == "hardlinked_output":
        copy = work / result["outputs"][row["path"]]
        copy.unlink()
        copy.hardlink_to(work / row["path"])
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError):
        validate_analysis(work)


def test_equivalent_copies_cannot_hide_changed_network_values(work):
    result = load(work, RESULTS)
    row = result["studies"][0]
    path = work / row["path"]
    value = read_touchstone(work, row["path"])
    value.s = value.s * 0.5
    path.write_text(value.write_touchstone(return_string=True, version="2.0", write_noise=False))
    shutil.copyfile(path, work / result["outputs"][row["path"]])
    with pytest.raises(EvidenceError, match="recomputation"):
        validate_analysis(work)


def test_physical_mutation_fails_original_bounds_after_genuine_recalculation(planned):
    plan = load(planned)
    plan["networks"]["match"]["elements"][0]["value_si"] *= 2
    save(planned, plan)
    with pytest.raises(EvidenceError, match="match/input_match.*outside"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert result["status"] == "failed"
    assert len(result["studies"]) == 6
    assert (planned / result["inputs"][PLAN]).read_bytes() == (planned / PLAN).read_bytes()


def test_existing_results_are_preserved(work):
    original = (work / RESULTS).read_bytes()
    with pytest.raises(FileExistsError):
        run_analysis(work)
    assert (work / RESULTS).read_bytes() == original
    assert validate_analysis(work)


@pytest.mark.parametrize("field", ["kind", "metric", "statistic", "unit", "ports", "minimum", "at_hz"])
@pytest.mark.parametrize("invalid", [None, {}, [], True])
def test_invalid_json_fields_have_explicit_errors(planned, field, invalid):
    plan = load(planned)
    if field == "kind":
        plan["networks"]["attenuator"]["kind"] = invalid
    else:
        plan["studies"][0]["checks"][0][field] = invalid
    save(planned, plan)
    with pytest.raises(EvidenceError):
        run_analysis(planned)


@pytest.mark.parametrize("mutation,reason", [
    ("cycle", "cyclic"), ("unknown", "unknown network"), ("grid", "grids differ"),
    ("junction", "references differ"), ("port_permutation", "permutation"),
    ("bad_element", "finite number"), ("bad_frequency", "increasing"), ("bad_reference", "positive"),
])
def test_graph_and_physical_conventions_fail_explicitly(planned, mutation, reason):
    plan = load(planned)
    nodes = plan["networks"]
    if mutation == "cycle":
        nodes["twice"]["inputs"] = ["twice", "attenuator"]
    elif mutation == "unknown":
        nodes["twice"]["inputs"] = ["missing", "attenuator"]
    elif mutation == "grid":
        nodes["resistor"]["frequency_hz"] = [0.5e9, 1e9, 2e9]
        nodes["twice"]["inputs"] = ["resistor", "attenuator"]
    elif mutation == "junction":
        nodes["twice"]["inputs"] = ["resistor_75", "attenuator"]
    elif mutation == "port_permutation":
        nodes["twice"] = {"kind": "reorder", "input": "attenuator", "ports": [1, 1]}
    elif mutation == "bad_element":
        nodes["resistor"]["elements"][0]["value_si"] = -1
    elif mutation == "bad_frequency":
        nodes["resistor"]["frequency_hz"] = [1e9, 1e9]
    else:
        nodes["resistor"]["z0_ohm"] = [50, 0]
    save(planned, plan)
    with pytest.raises(EvidenceError, match=reason):
        validate_plan(planned)


def test_full_matrix_passivity_catches_correlated_excitation_gain():
    s = np.array([[[0.8, 0.5], [0.5, 0.8]]], dtype=complex)
    assert np.all(np.sum(abs(s)**2, axis=1) < 1)
    network = rf.Network(f=[1e9], s=s, z0=50)
    value, unit = measure(network, {"metric": "sigma_max", "statistic": "at", "at_hz": 1e9})
    assert value == pytest.approx(1.3) and unit == "1"


def test_unequal_real_references_and_ideal_thru_do_not_need_singular_z_conversion(planned):
    nodes = load(planned)["networks"]
    nodes["quarter_wave"]["delay_s"] = 0
    nodes["changed"] = {"kind": "renormalize", "input": "quarter_wave", "z0_ohm": [50, 75]}
    nodes["back"] = {"kind": "renormalize", "input": "changed", "z0_ohm": [50, 50]}
    networks, _ = build_networks(planned, nodes, ["back"])
    mismatch = networks["changed"]
    assert np.allclose(mismatch.s[:, 0, 0], 0.2, atol=1e-14)
    assert np.allclose(mismatch.s[:, 1, 1], -0.2, atol=1e-14)
    assert np.allclose(mismatch.s[:, 1, 0], 2 * math.sqrt(50 * 75) / 125, atol=1e-14)
    assert np.allclose(networks["back"].s, networks["quarter_wave"].s, atol=1e-14)


def test_three_port_permutation_moves_both_s_axes_and_references(tmp_path):
    original = rf.Network(f=[1e9], s=np.arange(9).reshape(1, 3, 3) / 100, z0=[50, 60, 70], name="three")
    path = tmp_path / "three.ts"
    path.write_text(original.write_touchstone(return_string=True, version="2.0", write_noise=False))
    nodes = {
        "source": {"kind": "touchstone", "path": "three.ts", "ports": ["a", "b", "c"],
                   "source": "synthetic parser test", "validity": "one frequency", "limitations": ["not measured"]},
        "ordered": {"kind": "reorder", "input": "source", "ports": [3, 1, 2]},
    }
    networks, _ = build_networks(tmp_path, nodes)
    expected = original.s[:, [2, 0, 1], :][:, :, [2, 0, 1]]
    assert np.array_equal(networks["ordered"].s, expected)
    assert np.array_equal(networks["ordered"].z0, [[70, 50, 60]])
    assert networks["ordered"].port_names == ["c", "a", "b"]


@pytest.mark.parametrize("form,values", [("RI", "0.5 0"), ("MA", "0.5 0"), ("DB", "-6.020599913279624 0")])
def test_touchstone_1_formats_and_2_reference_round_trip(tmp_path, form, values):
    (tmp_path / "one.s1p").write_text(f"# GHz S {form} R 75\n1 {values}\n2 {values}\n")
    network = read_touchstone(tmp_path, "one.s1p")
    assert np.allclose(network.s[:, 0, 0], 0.5)
    assert np.array_equal(network.f, [1e9, 2e9])
    (tmp_path / "two.ts").write_text(network.write_touchstone(return_string=True, version="2.0", write_noise=False))
    restored = read_touchstone(tmp_path, "two.ts")
    assert np.array_equal(restored.z0, [[75], [75]])
    assert np.array_equal(restored.s, network.s)


@pytest.mark.parametrize("content", [
    "1 0.5 0\n", "# GHz Z RI R 50\n1 0.5 0\n", "# GHz S RI R 50\n1 nan 0\n",
    "# GHz S RI R 50\n2 0.5 0\n1 0.5 0\n", "# GHz S RI R 50\n1 0.5\n",
    "[Version] 2.0\n# GHz S RI R 50\n[Number of Ports] 1000\n",
])
def test_bad_touchstone_is_not_silently_reinterpreted(tmp_path, content):
    (tmp_path / "bad.s1p").write_text(content)
    with pytest.raises(EvidenceError):
        read_touchstone(tmp_path, "bad.s1p")


def test_serialized_network_and_external_paths_are_rejected(tmp_path):
    (tmp_path / "bad.ntwk").write_bytes(b"not a Touchstone file")
    with pytest.raises(EvidenceError, match="serialized"):
        read_touchstone(tmp_path, "bad.ntwk")
    with pytest.raises(EvidenceError, match="project-relative"):
        read_touchstone(tmp_path, "../outside.s2p")


def test_touchstone_declared_counts_must_match_data(tmp_path):
    network = rf.Network(f=[1e9, 2e9], s=np.zeros((2, 1, 1)), z0=50, name="count")
    data = network.write_touchstone(return_string=True, version="2.0", write_noise=False)
    (tmp_path / "count.ts").write_text(data.replace("[Number of Frequencies] 2", "[Number of Frequencies] 3"))
    with pytest.raises(EvidenceError, match="disagrees"):
        read_touchstone(tmp_path, "count.ts")


@pytest.mark.parametrize("reference", [50 + 1j, np.array([[50], [75]])])
def test_unsupported_reference_conventions_are_explicit(reference):
    network = rf.Network(f=[1e9, 2e9], s=np.zeros((2, 1, 1)), z0=reference)
    with pytest.raises(EvidenceError, match="reference"):
        validate_network(network)


def test_direct_reference_conversion_agrees_with_skrf_for_nonsingular_multiports(tmp_path):
    rng = np.random.default_rng(19)
    matrix = (rng.normal(size=(2, 3, 3)) + 1j * rng.normal(size=(2, 3, 3))) * 0.08
    original = rf.Network(f=[1e9, 2e9], s=matrix, z0=[40, 50, 60], name="multi")
    (tmp_path / "multi.ts").write_text(original.write_touchstone(return_string=True, version="2.0", write_noise=False))
    base = {
        "kind": "touchstone", "path": "multi.ts", "ports": ["a", "b", "c"],
        "source": "synthetic numeric test", "validity": "two samples", "limitations": ["not measured"],
    }
    nodes = {
        "original": base,
        "changed": {"kind": "renormalize", "input": "original", "z0_ohm": [25, 75, 100]},
        "back": {"kind": "renormalize", "input": "changed", "z0_ohm": [40, 50, 60]},
    }
    networks, _ = build_networks(tmp_path, nodes)
    expected = original.copy()
    expected.renormalize([25, 75, 100], s_def="power")
    np.testing.assert_allclose(networks["changed"].s, expected.s, atol=1e-13, rtol=1e-13)
    np.testing.assert_allclose(networks["back"].s, original.s, atol=1e-13, rtol=1e-13)


def test_band_extrema_and_phase_unwrap():
    phases = np.arange(170, 751, 20)
    network = rf.Network(
        f=np.arange(1, len(phases) + 1) * 1e9,
        s=np.exp(1j * np.deg2rad(phases)).reshape(-1, 1, 1), z0=50,
    )
    check = {"metric": "s_phase_deg", "ports": [1, 1], "statistic": "max", "window_hz": [1e9, 30e9]}
    value, unit = measure(network, check)
    assert value == pytest.approx(750) and unit == "deg"
    assert measure(network, {**check, "statistic": "min"})[0] == pytest.approx(170)


def test_zero_logarithms_and_out_of_band_measurements_are_errors():
    network = rf.Network(f=[1e9, 2e9], s=np.zeros((2, 1, 1)), z0=50)
    check = {"metric": "s_magnitude", "ports": [1, 1], "statistic": "at", "at_hz": 1e9}
    assert measure(network, check) == (0, "1")
    for metric in ("s_db", "s_phase_deg"):
        with pytest.raises(EvidenceError):
            measure(network, {**check, "metric": metric})
    with pytest.raises(EvidenceError, match="outside"):
        measure(network, {**check, "at_hz": 0.9e9})


def test_real_role_builders_receive_the_canonical_contract(tmp_path):
    from argus.roles.prompts import resolve_role_prompt
    from argus.roles.prompts.engineer import mission_request
    from argus.roles.prompts.manager import stage_decision_request
    from argus.roles.prompts.planner import PLAN_PREVIEW, continuous_request
    from argus.roles.prompts.reviewer import evaluate_request

    state, project = tmp_path / "state", tmp_path / "project"
    project.mkdir()
    persist_vertical(state, "rf_design", workflow_profile="analysis")
    requests = [
        stage_decision_request(state, stage=current_stage(state)),
        continuous_request(state, operation=PLAN_PREVIEW, altitude_root=project, include_search_altitude=False),
        mission_request(state, altitude_root=project, stage=current_stage(state)),
        evaluate_request(state, altitude_root=project),
    ]
    canonical = Path(stages.__file__).with_name("evidence-contract.md").read_text()
    for request in requests:
        prompt = resolve_role_prompt(request)
        assert prompt.stage_order == ("analysis",)
        assert canonical in prompt.role_banner
        assert stages.evidence_check_command("rf_design", "analysis") in prompt.role_banner
