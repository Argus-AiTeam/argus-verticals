"""Validate explicit SI package geometry, thermal conditions and original bounds."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path


class EvidenceError(ValueError):
    pass


def project_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise EvidenceError(f"expected a project-relative file, got {relative!r}")
    try:
        path = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"{relative}: {exc}") from exc
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size == 0:
        raise EvidenceError(f"{relative}: expected a nonempty file inside the project")
    return path


def record(root: Path, relative: str) -> dict:
    try:
        value = json.loads(project_file(root, relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{relative}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{relative}: expected a JSON object")
    return value


def names(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise EvidenceError(f"{field}: expected distinct nonempty strings")
    return value


def number(value: object, field: str, *, minimum: float = 0) -> float:
    message = f"{field}: expected a finite number >= {minimum}"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(message)
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise EvidenceError(message) from exc
    if not finite or value < minimum:
        raise EvidenceError(message)
    return value


def current_files(root: Path, payload: dict, required: list[str], *, field: str = "inputs") -> None:
    copies = payload.get(field)
    if not isinstance(copies, dict) or not set(required) <= copies.keys():
        raise EvidenceError(f"{field}: snapshots must include every required file")
    for source, snapshot in copies.items():
        source_path, copy_path = project_file(root, source), project_file(root, snapshot)
        if source_path.samefile(copy_path) or source_path.read_bytes() != copy_path.read_bytes():
            raise EvidenceError(f"{field}: missing independent copy or changed file {source}")


PLAN = "package/PLAN.json"
RESULTS_DIR = "package/results"
INPUTS_DIR = RESULTS_DIR + "/inputs"
RESULTS = RESULTS_DIR + "/RESULTS.json"
METRICS = {
    "temperature_max_k": "K", "top_mean_k": "K", "theta_top_k_w": "K/W",
    "bottom_heat_w": "W", "energy_relative_error": "1",
    "convective_heat_w": "W", "convection_area_m2": "m2",
}
CONVECTION_SURFACES = {"bottom", "top", "other_exposed"}


def temperature_offset(run: dict) -> float:
    return run["convection"]["ambient_temperature_k"] if "convection" in run else 0.0


def text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field}: expected nonempty text")
    return value


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value):
        raise EvidenceError("identifier: use a lowercase letter followed by at most 31 letters, digits or underscores")
    return value


def bounded(value: object, field: str, low: float, high: float) -> float:
    result = number(value, field, minimum=low)
    if result > high:
        raise EvidenceError(f"{field}: exceeds supported maximum {high:g}")
    return result


def validate_specification(root: Path) -> dict:
    plan = record(root, PLAN)
    text(plan.get("objective"), "objective")
    names(plan.get("limitations"), "limitations")
    requirements = plan.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise EvidenceError("requirements: map identifiers to observable requirements")
    for key, value in requirements.items():
        identifier(key)
        text(value, "requirement")
    return plan


def read_model(root: Path, relative: object) -> dict:
    path = text(relative, "model path")
    if Path(path).as_posix() != path or path.startswith(RESULTS_DIR + "/"):
        raise EvidenceError("model: use a canonical input path outside results")
    model = record(root, path)
    if model.get("length_unit") != "m" or model.get("temperature_unit") != "K":
        raise EvidenceError("model: explicitly use metres and kelvin")
    text(model.get("source"), "model source")
    text(model.get("validity"), "model validity")
    names(model.get("limitations"), "model limitations")
    layers = model.get("layers")
    if not isinstance(layers, list) or not 1 <= len(layers) <= 8:
        raise EvidenceError("model: declare 1-8 centred rectangular layers, bottom to top")
    ids = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise EvidenceError("layer must be an object")
        ids.append(identifier(layer.get("id")))
        size = layer.get("size_xy_m")
        if not isinstance(size, list) or len(size) != 2:
            raise EvidenceError("size_xy_m: provide [width, depth] in metres")
        for value in size:
            bounded(value, "lateral dimension", 1e-5, 0.1)
        bounded(layer.get("thickness_m"), "thickness_m", 1e-5, 0.1)
        bounded(layer.get("conductivity_w_mk"), "conductivity_w_mk", 1e-3, 1e4)
        text(layer.get("material_source"), "material_source")
    names(ids, "layer ids")
    if sum(layer["thickness_m"] for layer in layers) > 0.1:
        raise EvidenceError("total model thickness exceeds 0.1 m")
    return model


def spreading(model: dict) -> bool:
    return any(layer["size_xy_m"] != model["layers"][0]["size_xy_m"] for layer in model["layers"][1:])


def validate_model(root: Path) -> dict:
    plan = validate_specification(root)
    models = names(plan.get("models"), "models")
    if len(models) > 8:
        raise EvidenceError("at most eight model files are supported")
    for relative in models:
        read_model(root, relative)
    return plan


def validate_plan(root: Path) -> tuple[dict, dict, list[str]]:
    plan = validate_specification(root)
    declared = names(plan.get("models"), "models")
    if len(declared) > 8:
        raise EvidenceError("at most eight model files are supported")
    runs = plan.get("runs")
    if not isinstance(runs, list) or not 1 <= len(runs) <= 8 or any(not isinstance(r, dict) for r in runs):
        raise EvidenceError("runs: declare 1-8 native thermal studies")
    ids, covered, models = [], set(), {}
    for run in runs:
        ids.append(identifier(run.get("id")))
        relative = text(run.get("model"), "run.model")
        if relative not in declared:
            raise EvidenceError("run model is not declared")
        model = models.setdefault(relative, read_model(root, relative))
        mesh = bounded(run.get("mesh_size_m"), "mesh_size_m", 1e-5, 0.1)
        estimate = 0.0
        for layer in model["layers"]:
            x, y = layer["size_xy_m"]
            z = layer["thickness_m"]
            estimate += 12 * x*y*z/mesh**3 + 8 * (x*y+x*z+y*z)/mesh**2
        if estimate > 50000:
            raise EvidenceError("requested mesh exceeds the conservative 50000-element estimate")
        bounded(run.get("power_w"), "power_w", 1e-6, 1e4)
        if "convection" in run:
            convection = run["convection"]
            if "base_temperature_k" in run:
                raise EvidenceError("choose fixed bottom temperature or convection, not both")
            if not isinstance(convection, dict) or set(convection) != {
                "ambient_temperature_k", "coefficient_w_m2k", "surfaces", "source",
            }:
                raise EvidenceError("convection needs ambient_temperature_k, coefficient_w_m2k, surfaces and source")
            bounded(convection["ambient_temperature_k"], "ambient_temperature_k", 1, 2000)
            bounded(convection["coefficient_w_m2k"], "coefficient_w_m2k", 1e-3, 1e6)
            surfaces = names(convection["surfaces"], "convection surfaces")
            if not set(surfaces) <= CONVECTION_SURFACES:
                raise EvidenceError("convection surfaces must be bottom, top or other_exposed")
            text(convection["source"], "convection source")
        else:
            bounded(run.get("base_temperature_k"), "base_temperature_k", 1, 2000)
        checks = run.get("checks")
        if not isinstance(checks, list) or not 1 <= len(checks) <= 32:
            raise EvidenceError("each run needs 1-32 original numerical checks")
        check_ids = []
        for check in checks:
            if not isinstance(check, dict):
                raise EvidenceError("each check must be an object")
            check_ids.append(identifier(check.get("id")))
            requirement = identifier(check.get("requirement"))
            if requirement not in plan["requirements"]:
                raise EvidenceError("check references an unknown requirement")
            covered.add(requirement)
            metric = check.get("metric")
            if not isinstance(metric, str) or metric not in METRICS or check.get("unit") != METRICS[metric]:
                raise EvidenceError("check metric or unit is unsupported")
            if metric in ("convective_heat_w", "convection_area_m2") and "convection" not in run:
                raise EvidenceError("convection metrics require an explicit convection boundary")
            low = number(check.get("minimum"), "minimum", minimum=-math.inf)
            high = number(check.get("maximum"), "maximum", minimum=-math.inf)
            if low > high:
                raise EvidenceError("minimum exceeds maximum")
        names(check_ids, "check ids")
    names(ids, "run ids")
    if covered != set(plan["requirements"]):
        raise EvidenceError("every numerical requirement needs a declared check")
    pairs = plan.get("convergence", [])
    if not isinstance(pairs, list) or len(pairs) > 8:
        raise EvidenceError("convergence: declare at most eight coarse/fine comparisons")
    by_id = {run["id"]: run for run in runs}
    compared, pair_ids = set(), set()
    for pair in pairs:
        if not isinstance(pair, dict):
            raise EvidenceError("convergence comparison must be an object")
        if identifier(pair.get("coarse")) not in by_id or identifier(pair.get("fine")) not in by_id:
            raise EvidenceError("convergence must identify two declared runs")
        coarse, fine = by_id[pair["coarse"]], by_id[pair["fine"]]
        if pair.get("metric") not in ("temperature_max_k", "top_mean_k", "theta_top_k_w"):
            raise EvidenceError("compare temperature or thermal resistance under refinement")
        identity = (pair["coarse"], pair["fine"], pair.get("metric"))
        if identity in pair_ids:
            raise EvidenceError("duplicate convergence comparison")
        pair_ids.add(identity)
        if any(coarse.get(key) != fine.get(key) for key in ("model", "power_w", "base_temperature_k", "convection")):
            raise EvidenceError("mesh comparison must preserve model, load and all boundary conditions")
        if fine["mesh_size_m"] > 0.8 * coarse["mesh_size_m"]:
            raise EvidenceError("fine mesh size must be at most 80 percent of coarse")
        number(pair.get("max_delta"), "convergence max_delta")
        compared.update((pair["coarse"], pair["fine"]))
    if any(spreading(models[run["model"]]) and run["id"] not in compared for run in runs):
        raise EvidenceError("lateral spreading studies require an explicit mesh-refinement comparison")
    if any("convection" in run and run["id"] not in compared for run in runs):
        raise EvidenceError("convection studies require an explicit mesh-refinement comparison")
    return plan, models, sorted({PLAN, *(run["model"] for run in runs)})
