from __future__ import annotations

import json
import re
import shutil
import subprocess
from itertools import combinations
from pathlib import Path

import pytest
from argus.skills.stage_machine import StageCompletionError, complete_final_stage, current_stage
from argus.skills.vertical_select import persist_vertical, vertical_completion_certificate_status
from argus.verticals._base import load_vertical_contract

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.package_design import native, stages
from argus_verticals.package_design.evidence import validate_thermal
from argus_verticals.package_design.mesh import deck, read_mesh
from argus_verticals.package_design.model import (
    PLAN,
    RESULTS,
    read_model,
    validate_model,
    validate_plan,
)
from argus_verticals.package_design.run_analysis import run_analysis
from argus_verticals.package_design.run_reference import prepare_reference, run_reference


def load(root, relative=PLAN):
    return json.loads((root / relative).read_text())


def save(root, value, relative=PLAN):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if any(shutil.which(tool) is None for tool in ("gmsh", "ccx")):
        pytest.skip("native Gmsh and CalculiX are required")
    root = tmp_path_factory.mktemp("package") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    root = Path(shutil.copytree(reference, tmp_path / "work"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(reference), str(root)))
    return root


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture
def slab(planned):
    plan = load(planned)
    plan["runs"] = plan["runs"][:1]
    plan["requirements"] = {"slab": plan["requirements"]["slab"]}
    plan["convergence"] = []
    save(planned, plan)
    return planned


def test_real_equations_spreading_and_finite_completion(reference, tmp_path):
    values = validate_thermal(reference)
    for identity, resistance in (("slab", 1), ("stack", 1.5)):
        assert values[identity]["theta_top_k_w"] == pytest.approx(resistance, abs=0.001)
        assert values[identity]["temperature_max_k"] == pytest.approx(300+resistance, abs=0.001)
        assert values[identity]["bottom_heat_w"] == pytest.approx(1, abs=1e-6)
    assert abs(values["fine"]["temperature_max_k"]-values["coarse"]["temperature_max_k"]) <= 0.15
    assert values["fine"]["temperature_max_k"] > values["stack"]["temperature_max_k"]
    assert all(row["energy_relative_error"] <= 1e-5 for row in values.values())
    result = load(reference, RESULTS)
    assert len(result["runs"]) == 4 and len(result["outputs"]) == 24 and len(result["inputs"]) == 4
    assert result["versions"] == native.versions()
    for row in result["runs"]:
        assert [command["tool"] for command in row["commands"]] == ["gmsh", "calculix"]
        assert all(command["exit_code"] == 0 for command in row["commands"])
    state = tmp_path / "state"
    persist_vertical(state, "package_design", workflow_profile="thermal")
    complete_final_stage(state, reason="native reference equations checked", evidence_root=reference)
    assert vertical_completion_certificate_status(state, "package_design")["ok"]
    assert not (reference / "package/REVIEW.md").exists()


def test_only_selected_models_are_required(slab):
    plan = load(slab)
    plan["models"].append("missing.json")
    save(slab, plan)
    _, _, inputs = validate_plan(slab)
    assert inputs == ["design/slab.json", PLAN]
    assert set(run_analysis(slab)) == {"slab"}
    with pytest.raises(EvidenceError):
        validate_model(slab)


def test_all_custom_scopes_and_early_requirements(planned):
    contract = load_vertical_contract("package_design")
    assert stages.VERTICAL_SKILL_PARENTS == ()
    for count in range(1, 5):
        for selected in combinations(stages.STAGE_ORDER, count):
            expected = set(selected) | ({"thermal"} if "review" in selected else set())
            assert contract.compose_workflow(selected).stage_order == tuple(s for s in stages.STAGE_ORDER if s in expected)
    plan = load(planned)
    plan.pop("runs")
    save(planned, plan)
    assert not stages.stage_completion_issues("model", planned)
    plan.pop("models")
    save(planned, plan)
    assert not stages.stage_completion_issues("specification", planned)
    assert stages.stage_completion_issues("thermal", planned)


def test_review_and_missing_results_remain_distinct(work, tmp_path):
    assert stages.stage_completion_issues("review", work)
    (work / "package/REVIEW.md").write_text("Only the ideal steady thermal model was checked; no physical qualification.\n")
    assert not stages.stage_completion_issues("review", work)
    state = tmp_path / "missing"
    persist_vertical(state, "package_design", workflow_profile="thermal")
    with pytest.raises(StageCompletionError):
        complete_final_stage(state, reason="no calculation")


@pytest.mark.parametrize("change", ["power", "conductivity", "thickness"])
def test_real_physical_changes_fail_original_bounds_and_preserve_attempt(slab, change):
    if change == "power":
        plan = load(slab)
        plan["runs"][0]["power_w"] = 2
        save(slab, plan)
    else:
        model = load(slab, "design/slab.json")
        key, value = ("conductivity_w_mk", 5) if change == "conductivity" else ("thickness_m", 0.002)
        model["layers"][0][key] = value
        save(slab, model, "design/slab.json")
    with pytest.raises(EvidenceError, match="outside original bounds"):
        run_analysis(slab)
    result = load(slab, RESULTS)
    assert result["status"] == "failed" and len(result["outputs"]) == 6
    assert all(row["exit_code"] == 0 for row in result["runs"][0]["commands"])
    with pytest.raises(FileExistsError):
        run_analysis(slab)


def test_native_linearity_and_boundary_shift(slab):
    plan = load(slab)
    run = plan["runs"][0]
    run["power_w"], run["base_temperature_k"] = 2, 310
    run["checks"][0].update(minimum=311.999, maximum=312.001)
    save(slab, plan)
    values = run_analysis(slab)["slab"]
    assert values["temperature_max_k"] == pytest.approx(312, abs=0.001)
    assert values["theta_top_k_w"] == pytest.approx(1, abs=0.001)
    assert values["bottom_heat_w"] == pytest.approx(2, abs=1e-6)


def test_mesh_area_weights_and_solver_numeric_fields(reference):
    model = read_model(reference, "design/stack.json")
    mesh = read_mesh(reference / "package/results/native/stack/model.msh", model)
    assert sum(mesh.top_weights.values()) == pytest.approx(1, abs=1e-12)
    assert max(mesh.top_weights.values()) > 2 * min(mesh.top_weights.values())
    run = load(reference)["runs"][1]
    data = deck(mesh, model, run)
    for line in data.splitlines():
        if re.match(r"^\d+,", line):
            assert all(len(field) <= 20 for field in line.split(","))
    assert "*HEAT TRANSFER,STEADY STATE" in data and "*CFLUX" in data


@pytest.mark.parametrize("mutation", [
    "plan", "model", "missing_input", "missing_copy", "self_copy", "hardlink",
    "status", "operation", "version", "missing_run", "run_order", "command",
    "cwd", "exit_code", "missing_log", "missing_output", "changed_output",
    "changed_retained", "hardlinked_output",
])
def test_current_evidence_rejects_stale_and_invalid_records(work, mutation):
    result = load(work, RESULTS)
    if mutation in ("plan", "model"):
        relative = PLAN if mutation == "plan" else "design/slab.json"
        with (work / relative).open("a") as handle:
            handle.write("\n")
    elif mutation == "missing_input":
        (work / "design/slab.json").unlink()
    elif mutation in ("missing_copy", "hardlink"):
        copy = work / result["inputs"][PLAN]
        copy.unlink()
        if mutation == "hardlink":
            copy.hardlink_to(work / PLAN)
    elif mutation == "self_copy":
        result["inputs"][PLAN] = PLAN
    elif mutation == "status":
        result["status"] = "failed"
    elif mutation == "operation":
        result["operation"] = "invented"
    elif mutation == "version":
        result["versions"]["calculix"] = "2.00"
    elif mutation == "missing_run":
        result["runs"].pop()
    elif mutation == "run_order":
        result["runs"].reverse()
    elif mutation == "command":
        result["runs"][0]["commands"][0]["command"] = ["true"]
    elif mutation == "cwd":
        result["runs"][0]["commands"][0]["cwd"] = "/elsewhere"
    elif mutation == "exit_code":
        result["runs"][0]["commands"][0]["exit_code"] = False
    elif mutation == "missing_log":
        Path(result["runs"][0]["commands"][0]["log"]).unlink()
    else:
        source, retained = next(iter(result["outputs"].items()))
        if mutation == "missing_output":
            (work / source).unlink()
        elif mutation == "changed_output":
            (work / source).write_text("changed\n")
        elif mutation == "changed_retained":
            (work / retained).write_text("changed\n")
        else:
            (work / retained).unlink()
            (work / retained).hardlink_to(work / source)
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError):
        validate_thermal(work)


def test_matching_copies_cannot_hide_fabricated_native_temperature(work):
    result = load(work, RESULTS)
    source = "package/results/native/slab/thermal.dat"
    path = work / source
    assert "3.010000E+02" in path.read_text()
    path.write_text(path.read_text().replace("3.010000E+02", "3.010005E+02"))
    shutil.copyfile(path, work / result["outputs"][source])
    with pytest.raises(EvidenceError, match="independent replay"):
        validate_thermal(work)


@pytest.mark.parametrize("name", ["model.geo", "thermal.inp", "thermal.frd"])
def test_modified_generated_files_are_not_accepted_even_with_matching_copies(work, name):
    result = load(work, RESULTS)
    source = f"package/results/native/slab/{name}"
    path = work / source
    path.write_text(path.read_text() + "\nmodified\n")
    shutil.copyfile(path, work / result["outputs"][source])
    with pytest.raises(EvidenceError, match="differs"):
        validate_thermal(work)


@pytest.mark.parametrize("mutation", ["nonfinite", "missing_node", "duplicate_node", "wrong_time", "extra_step", "wrong_set", "malformed"])
def test_native_field_reader_is_strict(reference, tmp_path, mutation):
    model = read_model(reference, "design/slab.json")
    mesh = read_mesh(reference / "package/results/native/slab/model.msh", model)
    text = (reference / "package/results/native/slab/thermal.dat").read_text()
    first = re.search(r"^\s*1\s+[0-9.E+-]+\s*$", text, re.MULTILINE).group()
    if mutation == "nonfinite":
        text = text.replace("3.000000E+02", "NaN", 1)
    elif mutation == "missing_node":
        text = text.replace(first, "", 1)
    elif mutation == "duplicate_node":
        text = text.replace(first, first + "\n" + first, 1)
    elif mutation == "wrong_time":
        text = text.replace("0.1000000E+01", "0.5000000E+00")
    elif mutation == "extra_step":
        text += text
    elif mutation == "wrong_set":
        text = text.replace("for set ALL", "for set OTHER", 1)
    else:
        text = text.replace(first, "not a numeric field", 1)
    path = tmp_path / "thermal.dat"
    path.write_text(text)
    with pytest.raises(EvidenceError):
        native.read_fields(path, mesh)


@pytest.mark.parametrize("mutation", ["binary", "oversize_count", "missing_end", "duplicate_node", "wrong_material", "missing_boundary"])
def test_native_mesh_reader_is_strict(reference, tmp_path, mutation):
    model = read_model(reference, "design/slab.json")
    text = (reference / "package/results/native/slab/model.msh").read_text()
    if mutation == "binary":
        text = text.replace("2.2 0 8", "2.2 1 8")
    elif mutation == "oversize_count":
        text = re.sub(r"\$Nodes\n\d+", "$Nodes\n20001", text)
    elif mutation == "missing_end":
        text = text.replace("$EndNodes", "$InvalidEnd")
    elif mutation == "duplicate_node":
        lines = text.splitlines()
        start = lines.index("$Nodes")
        lines[start+3] = lines[start+2]
        text = "\n".join(lines)
    else:
        lines = text.splitlines()
        start = lines.index("$Elements")
        for i in range(start+2, start+2+int(lines[start+1])):
            fields = lines[i].split()
            if (mutation == "wrong_material" and fields[1] == "4") or (mutation == "missing_boundary" and fields[1] == "2"):
                fields[3] = "99"
                lines[i] = " ".join(fields)
                break
        text = "\n".join(lines)
    path = tmp_path / "bad.msh"
    path.write_text(text)
    with pytest.raises(EvidenceError):
        read_mesh(path, model)


@pytest.mark.parametrize("mutation", [
    "zero_power", "bool_power", "nonfinite_power", "mesh_budget", "unknown_model", "duplicate_run",
    "missing_requirement", "wrong_unit", "bad_metric_type", "reversed_bounds", "missing_refinement",
    "not_finer", "different_load", "negative_delta", "wrong_pair", "duplicate_pair",
    "length_unit", "temperature_unit", "zero_k", "bad_size", "duplicate_layer", "too_thin", "missing_source",
])
def test_invalid_models_conditions_and_refinement_fail_explicitly(planned, mutation):
    plan = load(planned)
    first = plan["runs"][0]
    if mutation in ("zero_power", "bool_power", "nonfinite_power"):
        first["power_w"] = {"zero_power": 0, "bool_power": True, "nonfinite_power": float("inf")}[mutation]
    elif mutation == "mesh_budget":
        first["mesh_size_m"] = 1e-5
    elif mutation == "unknown_model":
        first["model"] = "unknown.json"
    elif mutation == "duplicate_run":
        plan["runs"][1]["id"] = first["id"]
    elif mutation == "missing_requirement":
        first["checks"][0]["requirement"] = "unknown"
    elif mutation == "wrong_unit":
        first["checks"][0]["unit"] = "C"
    elif mutation == "bad_metric_type":
        first["checks"][0]["metric"] = []
    elif mutation == "reversed_bounds":
        first["checks"][0].update(minimum=500, maximum=400)
    elif mutation == "missing_refinement":
        plan["convergence"] = []
    elif mutation == "not_finer":
        plan["runs"][3]["mesh_size_m"] = 0.0009
    elif mutation == "different_load":
        plan["runs"][3]["power_w"] = 2
    elif mutation == "negative_delta":
        plan["convergence"][0]["max_delta"] = -1
    elif mutation == "wrong_pair":
        plan["convergence"][0]["fine"] = []
    elif mutation == "duplicate_pair":
        plan["convergence"] *= 2
    else:
        model = load(planned, "design/slab.json")
        if mutation in ("length_unit", "temperature_unit"):
            model[mutation] = "mm" if mutation == "length_unit" else "C"
        elif mutation == "zero_k":
            model["layers"][0]["conductivity_w_mk"] = 0
        elif mutation == "bad_size":
            model["layers"][0]["size_xy_m"] = [0.01]
        elif mutation == "duplicate_layer":
            model["layers"] *= 2
        elif mutation == "too_thin":
            model["layers"][0]["thickness_m"] = 1e-8
        else:
            model["layers"][0]["material_source"] = ""
        save(planned, model, "design/slab.json")
    save(planned, plan)
    with pytest.raises(EvidenceError):
        validate_plan(planned)


def test_original_refinement_limit_is_enforced(work):
    plan, result = load(work), load(work, RESULTS)
    plan["convergence"][0]["max_delta"] = 1e-6
    save(work, plan)
    shutil.copyfile(work / PLAN, work / result["inputs"][PLAN])
    with pytest.raises(EvidenceError, match="mesh comparison delta"):
        validate_thermal(work)


def test_missing_native_tool_is_an_explicit_failure(slab, monkeypatch):
    monkeypatch.setenv("PATH", "")
    with pytest.raises(EvidenceError, match="native gmsh is required"):
        run_analysis(slab)
    assert not (slab / RESULTS).exists()


def test_zero_exit_with_native_error_is_not_success(slab, tmp_path, monkeypatch):
    plan, models, _ = validate_plan(slab)
    monkeypatch.setattr(native.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "", "Error : meshing failed\n"))
    output = tmp_path / "native"
    with pytest.raises(EvidenceError, match="did not complete successfully"):
        native.execute(models["design/slab.json"], plan["runs"][0], output)
    assert "meshing failed" in (output / "gmsh.log").read_text()


def test_checker_preserves_every_project_byte(reference):
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    validate_thermal(reference)
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}


def test_real_role_builders_receive_canonical_contract(tmp_path):
    from argus.roles.prompts import resolve_role_prompt
    from argus.roles.prompts.engineer import mission_request
    from argus.roles.prompts.manager import stage_decision_request
    from argus.roles.prompts.planner import PLAN_PREVIEW, continuous_request
    from argus.roles.prompts.reviewer import evaluate_request

    state, project = tmp_path / "state", tmp_path / "project"
    project.mkdir()
    persist_vertical(state, "package_design", workflow_profile="thermal")
    requests = [
        stage_decision_request(state, stage=current_stage(state)),
        continuous_request(state, operation=PLAN_PREVIEW, altitude_root=project, include_search_altitude=False),
        mission_request(state, altitude_root=project, stage=current_stage(state)),
        evaluate_request(state, altitude_root=project),
    ]
    canonical = Path(stages.__file__).with_name("evidence-contract.md").read_text()
    for request in requests:
        prompt = resolve_role_prompt(request)
        assert prompt.stage_order == ("thermal",)
        assert canonical in prompt.role_banner
        assert stages.evidence_check_command("package_design", "thermal") in prompt.role_banner
