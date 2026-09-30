"""Resolve a separately declared operating envelope without dropping any combinations."""
from __future__ import annotations

import copy
import itertools
import math
from dataclasses import dataclass
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, names, number, record

from .model import (
    METRICS,
    PLAN,
    RESULTS_DIR,
    _run,
    declared_models,
    estimated_points,
    fields,
    identifier,
    read_model,
    text,
    validate_checks,
    validate_model_values,
    validate_specification,
)

MAX_SCENARIOS = 17
MAX_ESTIMATED_POINTS = 1_500_000
MODEL_UNITS = {
    "inductance_h": "H", "capacitance_f": "F", "inductor_resistance_ohm": "ohm",
    "capacitor_esr_ohm": "ohm", "switch_on_resistance_ohm": "ohm",
    "switch_off_resistance_ohm": "ohm", "diode_saturation_current_a": "A",
    "diode_emission": "1", "diode_resistance_ohm": "ohm", "temperature_c": "degC",
}
RUN_UNITS = {
    "input_voltage_v": "V", "duty_cycle": "1", "frequency_hz": "Hz",
    "load_resistance_ohm": "ohm", "load_step.resistance_ohm": "ohm",
}
TARGETS = {**{f"model.{k}": v for k, v in MODEL_UNITS.items()}, **{f"run.{k}": v for k, v in RUN_UNITS.items()}}
CONDITIONS = {
    "input_voltage_v", "duty_cycle", "frequency_hz", "load_resistance_ohm",
    "load_step", "duration_s", "windows",
}
CHECK_FIELDS = {"id", "requirement", "window", "metric", "unit", "minimum", "maximum"}


@dataclass(frozen=True)
class Scenario:
    id: str
    coordinates: dict
    model: dict
    runs: tuple[dict, dict]


@dataclass(frozen=True)
class Study:
    specification: dict
    choices: dict
    inputs: tuple[str, ...]
    scenarios: tuple[Scenario, ...]
    grid_size: int

    @property
    def runs(self):
        return [(scenario, run) for scenario in self.scenarios for run in scenario.runs]


def _target(description: dict, *, factor: bool = False) -> str:
    target = description.get("target")
    if not isinstance(target, str) or target not in TARGETS:
        raise EvidenceError("unsupported operating-envelope target")
    if description.get("unit") != ("1" if factor else TARGETS[target]):
        raise EvidenceError(f"{target}: wrong explicit unit")
    text(description.get("source"), f"{target} source")
    return target


def _values(value: object, label: str, *, factor: bool = False) -> list:
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise EvidenceError(f"{label}: declare 1-8 finite distinct values")
    for item in value:
        number(item, label, minimum=0 if factor else -math.inf)
        if factor and item == 0:
            raise EvidenceError("tolerance factors must be positive")
    if len(set(value)) != len(value):
        raise EvidenceError(f"{label}: repeated values")
    return value


def _location(model: dict, run: dict, target: str) -> tuple[dict, str]:
    owner, key = target.split(".", 1)
    if owner == "model":
        return model, key
    if key == "load_step.resistance_ohm":
        if not isinstance(run.get("load_step"), dict):
            raise EvidenceError("a load-step target requires a declared load step")
        return run["load_step"], "resistance_ohm"
    return run, key


def resolve_study(root: Path) -> Study:
    plan = validate_specification(root)
    if "runs" in plan or "convergence" in plan:
        raise EvidenceError("robustness mode cannot also declare legacy runs or convergence")
    selected = fields(plan.get("robustness"), {"specification", "design"}, "robustness")
    relative = text(selected.get("specification"), "operating specification")
    if Path(relative).as_posix() != relative or relative.startswith(RESULTS_DIR + "/"):
        raise EvidenceError("operating specification must be a canonical input path outside results")
    specification = fields(record(root, relative), {
        "source", "limitations", "model", "conditions", "design_variables", "axes",
        "maximum_steps_s", "checks", "convergence", "goal",
    }, "operating specification")
    if specification.get("goal") not in ("diagnose", "design"):
        raise EvidenceError("operating specification goal must be diagnose or design")
    text(specification.get("source"), "operating specification source")
    names(specification.get("limitations"), "operating specification limitations")
    source = text(specification.get("model"), "nominal model")
    if source not in declared_models(plan):
        raise EvidenceError("nominal model must be declared by the plan")
    model = copy.deepcopy(read_model(root, source))
    conditions = copy.deepcopy(fields(specification.get("conditions"), CONDITIONS, "conditions"))
    design = selected.get("design")
    variables = specification.get("design_variables")
    if not isinstance(variables, dict) or not isinstance(design, dict) or set(design) != set(variables):
        raise EvidenceError("design must select exactly the declared design variables")
    if specification["goal"] == "diagnose" and variables:
        raise EvidenceError("diagnose fixes the supplied design; design variables require goal=design")
    selected_targets = set()
    for name, description in variables.items():
        identifier(name)
        fields(description, {"target", "unit", "source", "values", "minimum", "maximum"}, "design variable")
        target = _target(description)
        if target in selected_targets:
            raise EvidenceError("design variables cannot repeat a target")
        selected_targets.add(target)
        value = number(design[name], f"design.{name}", minimum=-math.inf)
        if "values" in description:
            if "minimum" in description or "maximum" in description or value not in _values(description["values"], name):
                raise EvidenceError(f"{name}: select one allowed design value")
        else:
            low = number(description.get("minimum"), "design minimum", minimum=-math.inf)
            high = number(description.get("maximum"), "design maximum", minimum=-math.inf)
            if not low <= value <= high:
                raise EvidenceError(f"{name}: design choice lies outside original limits")
        owner, key = _location(model, conditions, target)
        owner[key] = value
    axes = specification.get("axes")
    if not isinstance(axes, list) or not 1 <= len(axes) <= 8:
        raise EvidenceError("axes: declare 1-8 explicit operating or tolerance dimensions")
    dimensions, axis_ids, axis_targets = [], [], set()
    for axis in axes:
        fields(axis, {"id", "target", "unit", "source", "values", "factors"}, "axis")
        axis_ids.append(identifier(axis.get("id")))
        factor = "factors" in axis
        if factor == ("values" in axis):
            raise EvidenceError("an axis declares either absolute values or relative factors")
        target = _target(axis, factor=factor)
        if target in axis_targets:
            raise EvidenceError("axes cannot repeat a target")
        if target in selected_targets and not factor:
            raise EvidenceError("an absolute axis must not replace a selected design variable")
        axis_targets.add(target)
        owner, key = _location(model, conditions, target)
        if key not in owner:
            raise EvidenceError(f"{target}: nominal value is missing")
        base = number(owner[key], f"{target} nominal", minimum=-math.inf)
        values = _values(axis["factors" if factor else "values"], axis["id"], factor=factor)
        if len(values) < 2:
            raise EvidenceError("each operating axis needs at least two distinct samples")
        if factor and (base <= 0 or target == "model.temperature_c"):
            raise EvidenceError("relative factors require a positive non-temperature nominal quantity")
        resolved = [base * v if factor else v for v in values]
        for value in resolved:
            number(value, f"{target} resolved", minimum=-math.inf)
        dimensions.append((axis, target, resolved))
    names(axis_ids, "axis ids")
    grid_size = math.prod(len(values) for _, _, values in dimensions)
    if grid_size > MAX_SCENARIOS:
        raise EvidenceError("Cartesian grid exceeds the supported 17-scenario budget; no combinations were dropped")
    steps = specification.get("maximum_steps_s")
    if not isinstance(steps, list) or len(steps) != 2:
        raise EvidenceError("maximum_steps_s: declare coarse and fine maximum steps")
    for step in steps:
        number(step, "maximum step")
    if not 0 < steps[1] <= steps[0] / 2:
        raise EvidenceError("fine maximum step must be at most half the coarse maximum step")
    checks = specification.get("checks")
    if not isinstance(checks, list) or not checks:
        raise EvidenceError("operating specification needs original numerical checks")
    plain_checks = []
    for check in checks:
        fields(check, CHECK_FIELDS | {"margin_lower", "margin_upper"}, "study check")
        plain_checks.append({k: v for k, v in check.items() if k in CHECK_FIELDS})
        lower = number(check.get("margin_lower", 0), "required lower margin")
        upper = number(check.get("margin_upper", 0), "required upper margin")
        low = number(check.get("minimum"), "minimum", minimum=-math.inf)
        high = number(check.get("maximum"), "maximum", minimum=-math.inf)
        if not math.isfinite(high-low) or lower + upper > high-low:
            raise EvidenceError("required margins do not fit inside the original bounds")
    base_run = {**conditions, "model": source, "checks": plain_checks}
    preview = {**base_run, "id": "nominal_coarse", "max_step_s": steps[0]}
    _run(preview, model)
    if validate_checks(preview, plan["requirements"]) != set(plan["requirements"]):
        raise EvidenceError("every requirement must be covered by the operating specification")
    comparisons = specification.get("convergence")
    if not isinstance(comparisons, list) or not 1 <= len(comparisons) <= 32:
        raise EvidenceError("declare 1-32 operating-envelope time-step comparisons")
    compared = set()
    for comparison in comparisons:
        fields(comparison, {"window", "metric", "max_delta"}, "study comparison")
        window, metric = identifier(comparison.get("window")), comparison.get("metric")
        if not isinstance(metric, str) or metric not in METRICS:
            raise EvidenceError("unsupported study comparison metric")
        if not isinstance(conditions.get("windows"), dict) or window not in conditions["windows"]:
            raise EvidenceError("study comparison references an unknown window")
        if (window, metric) in compared:
            raise EvidenceError("duplicate study comparison")
        compared.add((window, metric))
        number(comparison.get("max_delta"), "maximum comparison delta")
    if not {(c.get("window"), c.get("metric")) for c in plain_checks} <= compared:
        raise EvidenceError("every checked quantity needs its own time-step comparison")
    scenarios = []
    total_points = 0.0

    def append(identity, coordinates, effective_model, effective_run):
        nonlocal total_points
        validate_model_values(effective_model)
        runs = tuple({**copy.deepcopy(effective_run), "id": f"{identity}_{name}", "max_step_s": step}
                     for name, step in zip(("coarse", "fine"), steps))
        for run in runs:
            _run(run, effective_model)
            if validate_checks(run, plan["requirements"]) != set(plan["requirements"]):
                raise EvidenceError("every requirement must be covered by the operating specification")
            total_points += estimated_points(run["duration_s"], run["max_step_s"], run["frequency_hz"])
        scenarios.append(Scenario(identity, coordinates, effective_model, runs))

    append("nominal", {}, copy.deepcopy(model), copy.deepcopy(base_run))
    for index, values in enumerate(itertools.product(*(values for _, _, values in dimensions))):
        effective_model, effective_run = copy.deepcopy(model), copy.deepcopy(base_run)
        coordinates = {}
        for (axis, target, _), value in zip(dimensions, values):
            owner, key = _location(effective_model, effective_run, target)
            owner[key] = value
            coordinates[axis["id"]] = value
        if effective_model == model and effective_run == base_run:
            continue
        append(f"corner_{index:03d}", coordinates, effective_model, effective_run)
    if len(scenarios) > MAX_SCENARIOS or total_points > MAX_ESTIMATED_POINTS:
        raise EvidenceError("nominal plus full Cartesian coverage exceeds scenario or aggregate point budget")
    return Study(specification, copy.deepcopy(design), tuple(sorted({PLAN, relative, source})),
                 tuple(scenarios), grid_size)
