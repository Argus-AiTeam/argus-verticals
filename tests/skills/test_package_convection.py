from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.package_design import native
from argus_verticals.package_design.evidence import validate_thermal
from argus_verticals.package_design.model import PLAN, RESULTS, read_model
from argus_verticals.package_design.run_analysis import run_analysis
from argus_verticals.package_design.run_convection_reference import prepare_reference, run_reference


def load(root, relative=PLAN):
    return json.loads((root / relative).read_text())


def save(root, value, relative=PLAN):
    (root / relative).write_text(json.dumps(value, indent=2) + "\n")


@pytest.fixture
def planned(tmp_path):
    root = tmp_path / "planned"
    prepare_reference(root)
    return root


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    if any(shutil.which(tool) is None for tool in ("gmsh", "ccx")):
        pytest.skip("native Gmsh and CalculiX are required")
    root = tmp_path_factory.mktemp("package-convection") / "reference"
    run_reference(root)
    return root


@pytest.fixture
def work(reference, tmp_path):
    root = Path(shutil.copytree(reference, tmp_path / "work"))
    path = root / RESULTS
    path.write_text(path.read_text().replace(str(reference), str(root)))
    return root


def test_native_analytic_resistances_and_all_exposed_heat(reference):
    measured = validate_thermal(reference)
    for resolution in ("coarse", "fine"):
        bottom, top = measured[f"bottom_{resolution}"], measured[f"top_{resolution}"]
        assert bottom["temperature_max_k"] == pytest.approx(311, abs=1e-5)
        assert bottom["theta_top_k_w"] == pytest.approx(11, abs=1e-5)
        assert bottom["bottom_heat_w"] == pytest.approx(1, abs=1e-6)
        assert top["temperature_max_k"] == pytest.approx(310, abs=1e-5)
        assert top["theta_top_k_w"] == pytest.approx(10, abs=1e-5)
        assert top["bottom_heat_w"] == 0
        exposed = measured[f"exposed_{resolution}"]
        assert exposed["convection_area_m2"] == pytest.approx(0.00026, abs=1e-12)
        assert set(exposed["convection_heat_by_surface_w"]) == {"bottom", "top", "other_exposed"}
        assert all(value > 0 for value in exposed["convection_heat_by_surface_w"].values())
    assert all(values["convective_heat_w"] == pytest.approx(1, abs=1e-6) for values in measured.values())
    assert all(values["energy_relative_error"] <= 1e-5 for values in measured.values())


@pytest.mark.parametrize("mutation", [
    "both_boundaries", "no_sink", "zero_h", "bool_h", "nan_h", "bad_ambient",
    "unknown_surface", "duplicate_surface", "missing_source", "unknown_key", "not_object",
    "missing_refinement", "changed_h", "changed_ambient", "changed_surfaces",
])
def test_invalid_boundary_and_refinement_fail_before_native_work(planned, mutation):
    plan = load(planned)
    convection = plan["runs"][0]["convection"]
    if mutation == "both_boundaries":
        plan["runs"][0]["base_temperature_k"] = 300
    elif mutation == "no_sink":
        convection["surfaces"] = []
    elif mutation in ("zero_h", "bool_h", "nan_h"):
        convection["coefficient_w_m2k"] = {"zero_h": 0, "bool_h": True, "nan_h": float("nan")}[mutation]
    elif mutation == "bad_ambient":
        convection["ambient_temperature_k"] = 0
    elif mutation == "unknown_surface":
        convection["surfaces"] = ["interfaces"]
    elif mutation == "duplicate_surface":
        convection["surfaces"] *= 2
    elif mutation == "missing_source":
        convection["source"] = ""
    elif mutation == "unknown_key":
        convection["radiation"] = True
    elif mutation == "not_object":
        plan["runs"][0]["convection"] = []
    elif mutation == "missing_refinement":
        plan["convergence"] = plan["convergence"][1:]
    else:
        key, value = {
            "changed_h": ("coefficient_w_m2k", 500),
            "changed_ambient": ("ambient_temperature_k", 301),
            "changed_surfaces": ("surfaces", ["top"]),
        }[mutation]
        plan["runs"][1]["convection"][key] = value
    save(planned, plan)
    with pytest.raises(EvidenceError):
        run_analysis(planned)
    assert not (planned / RESULTS).exists()


def test_native_shift_preserves_tiny_rises_and_physical_ambient(planned):
    plan = load(planned)
    plan["runs"] = plan["runs"][:2]
    plan["convergence"] = plan["convergence"][:1]
    plan["requirements"] = {"bottom": "The original tiny-rise series resistance is 1.01 K/W."}
    for run in plan["runs"]:
        run["power_w"] = 1e-6
        run["convection"].update(ambient_temperature_k=350, coefficient_w_m2k=1e6)
        run["checks"] = [{"id": "tiny", "requirement": "bottom", "metric": "theta_top_k_w", "unit": "K/W",
                          "minimum": 1.009999, "maximum": 1.010001}]
    save(planned, plan)
    values = run_analysis(planned)
    for run in plan["runs"]:
        result = values[run["id"]]
        assert result["theta_top_k_w"] == pytest.approx(1.01, abs=1e-6)
        assert result["top_mean_k"] == pytest.approx(350+1.01e-6, abs=1e-11)
        assert result["energy_relative_error"] <= 1e-5
    assert all(row["temperature_reference_k"] == 350 for row in load(planned, RESULTS)["runs"])


def test_original_h_degradation_fails_bounds_and_retains_results(planned):
    plan = load(planned)
    plan["runs"] = plan["runs"][:2]
    plan["convergence"] = plan["convergence"][:1]
    plan["requirements"] = {"bottom": plan["requirements"]["bottom"]}
    for run in plan["runs"]:
        run["convection"]["coefficient_w_m2k"] = 500
    save(planned, plan)
    with pytest.raises(EvidenceError, match="outside original bounds"):
        run_analysis(planned)
    assert load(planned, RESULTS)["status"] == "failed"
    with pytest.raises(FileExistsError):
        run_analysis(planned)


def test_temperature_offset_cannot_be_forged(work):
    result = load(work, RESULTS)
    result["runs"][0]["temperature_reference_k"] = 0
    save(work, result, RESULTS)
    with pytest.raises(EvidenceError, match="temperature reference"):
        validate_thermal(work)


def test_matching_copies_cannot_hide_modified_native_rise(work):
    result = load(work, RESULTS)
    source = "package/results/native/bottom_coarse/thermal.dat"
    path = work / source
    text = path.read_text()
    assert "1.100000E+01" in text
    path.write_text(text.replace("1.100000E+01", "1.100001E+01", 1))
    shutil.copyfile(path, work / result["outputs"][source])
    with pytest.raises(EvidenceError, match="independent replay"):
        validate_thermal(work)


def test_native_convection_uses_exact_exterior_tetrahedron_faces(reference):
    plan = load(reference)
    for run in plan["runs"]:
        output = reference / "package/results/native" / run["id"]
        values, mesh = native.measurements(output, read_model(reference, run["model"]), run)
        data = (output / "thermal.inp").read_text()
        assert "*BOUNDARY" not in data and "** Native NT is temperature rise" in data
        expected = {
            (element, face) for group in run["convection"]["surfaces"]
            for element, face, _ in mesh.surfaces[group]
        }
        film = data.split("*FILM\n", 1)[1].split("*CFLUX", 1)[0].strip().splitlines()
        actual = {(int(line.split(",")[0]), int(line.split(",")[1][1:])) for line in film}
        assert actual == expected and len(actual) == len(film)
        assert values["convection_area_m2"] > 0


def test_convection_checker_leaves_every_project_byte_unchanged(reference):
    before = {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}
    validate_thermal(reference)
    assert before == {p.relative_to(reference): p.read_bytes() for p in reference.rglob("*") if p.is_file()}


def test_native_two_material_stack_has_series_conduction_and_film_resistance(planned):
    plan = load(planned)
    plan["models"] = ["design/stack.json"]
    plan["runs"] = plan["runs"][:2]
    plan["convergence"] = plan["convergence"][:1]
    plan["requirements"] = {"bottom": "Series slab resistances plus bottom film give 11.5 K/W."}
    for run in plan["runs"]:
        run["model"] = "design/stack.json"
        run["checks"] = [{"id": "series", "requirement": "bottom", "metric": "theta_top_k_w", "unit": "K/W",
                          "minimum": 11.49999, "maximum": 11.50001}]
    save(planned, plan)
    assert all(row["theta_top_k_w"] == pytest.approx(11.5, abs=1e-5) for row in run_analysis(planned).values())


def test_finished_message_does_not_override_nonzero_solver_exit(planned, monkeypatch):
    execute = native.subprocess.run

    def nonzero_solver(command, **kwargs):
        result = execute(command, **kwargs)
        if command == native.arguments("calculix"):
            assert result.returncode == 0 and "Job finished" in result.stdout
            return subprocess.CompletedProcess(command, 201, result.stdout, result.stderr)
        return result

    monkeypatch.setattr(native.subprocess, "run", nonzero_solver)
    with pytest.raises(EvidenceError, match="did not complete successfully"):
        run_analysis(planned)
    result = load(planned, RESULTS)
    assert result["status"] == "failed"
    assert result["runs"][0]["commands"][-1]["exit_code"] == 201
