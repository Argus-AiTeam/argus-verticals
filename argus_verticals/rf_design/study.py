"""Resolve complete finite component samples and explicit frequency-grid refinements."""
from __future__ import annotations

import copy
import itertools
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    names,
    number,
    project_file,
    record,
)

from .evidence import PLAN, RESULTS_DIR, validate_network_plan, validate_specification
from .networks import MAX_POINTS, identifier, positive, text

MAX_SCENARIOS = 17
MAX_SCATTERING_ENTRIES = 2_000_000
MAX_INPUT_BYTES = 4 * 1024 * 1024
CHECK_FIELDS = {
    "id", "requirement", "metric", "ports", "statistic", "at_hz", "window_hz",
    "unit", "minimum", "maximum", "margin_lower", "margin_upper", "max_delta",
}


def fields(value: object, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise EvidenceError(f"{label}: expected an object with only {sorted(allowed)}")
    return value


def refined_grid(original: list) -> list[float]:
    if not 2 <= len(original) <= (MAX_POINTS+1)//2:
        raise EvidenceError("robustness grids need 2-5001 original samples")
    result = []
    for left, right in zip(original, original[1:]):
        middle = left + (right-left)/2
        if not left < middle < right:
            raise EvidenceError("frequency midpoint is not representable as a distinct sample")
        result.extend((left, middle))
    return [*result, original[-1]]


@dataclass(frozen=True)
class Study:
    specification: dict
    choices: dict
    inputs: tuple[str, ...]
    definitions: dict
    scenarios: tuple[dict, ...]
    grid_size: int


def resolve_study(root: Path) -> Study:
    plan = validate_specification(root)
    fields(plan, {"objective", "requirements", "limitations", "robustness"}, "robustness plan")
    selected = fields(plan.get("robustness"), {"specification", "design"}, "robustness")
    relative = text(selected.get("specification"), "specification path")
    if Path(relative).as_posix() != relative or relative == PLAN or relative.startswith(RESULTS_DIR + "/"):
        raise EvidenceError("specification must be a canonical original input outside results")
    inputs = (PLAN, relative)
    if sum(project_file(root, path).stat().st_size for path in inputs) > MAX_INPUT_BYTES:
        raise EvidenceError("RF robustness inputs exceed 4 MiB")
    spec = fields(record(root, relative), {
        "goal", "source", "limitations", "networks", "parameters", "design_variables", "axes", "studies",
    }, "robustness specification")
    if spec.get("goal") not in ("diagnose", "design"):
        raise EvidenceError("goal must be diagnose or design")
    text(spec.get("source"), "specification source")
    names(spec.get("limitations"), "specification limitations")
    studies = spec.get("studies")
    if not isinstance(studies, list) or not 1 <= len(studies) <= 4:
        raise EvidenceError("robustness needs 1-4 selected studies")
    _, networks, _ = validate_network_plan(root, {
        "requirements": plan["requirements"], "networks": spec.get("networks"), "studies": studies,
    })
    definitions = {key: value for key, value in spec["networks"].items() if key in networks}
    for node in definitions.values():
        if node["kind"] == "touchstone":
            raise EvidenceError("robustness refines ideal models, not interpolated measured Touchstone data")
        if node["kind"] in ("lumped", "line"):
            refined_grid(node["frequency_hz"])
    parameters = spec.get("parameters")
    if not isinstance(parameters, dict) or not 1 <= len(parameters) <= 8:
        raise EvidenceError("parameters: declare 1-8 ideal lumped component targets")

    def valid_value(name: str, value: object) -> float:
        value = positive(value, name)
        definition = parameters[name]
        if not definition["minimum"] <= value <= definition["maximum"]:
            raise EvidenceError(f"{name}: value lies outside original component validity")
        return value

    nominal, targets = {}, set()
    for name, definition in parameters.items():
        identifier(name)
        fields(definition, {"network", "element", "nominal", "minimum", "maximum", "unit", "source"}, "parameter")
        network, index = definition.get("network"), definition.get("element")
        if not isinstance(network, str) or network not in definitions or definitions[network]["kind"] != "lumped":
            raise EvidenceError("parameter must target a selected ideal lumped network")
        elements = definitions[network]["elements"]
        if type(index) is not int or not 1 <= index <= len(elements) or (network, index) in targets:
            raise EvidenceError("parameter elements must be distinct one-based component indices")
        element = elements[index-1]
        if definition.get("unit") != {"R": "ohm", "L": "H", "C": "F"}[element["kind"]]:
            raise EvidenceError("parameter unit does not match its component kind")
        text(definition.get("source"), "component source")
        low, high = (positive(definition.get(key), f"component {key}") for key in ("minimum", "maximum"))
        if low > high:
            raise EvidenceError("component validity minimum exceeds maximum")
        value = valid_value(name, definition.get("nominal"))
        if value != element["value_si"]:
            raise EvidenceError("nominal component differs from the original network")
        nominal[name] = value
        targets.add((network, index))
    variables, choices = spec.get("design_variables"), selected.get("design")
    if not isinstance(variables, dict) or not isinstance(choices, dict) or set(choices) != set(variables):
        raise EvidenceError("design must choose exactly the declared common component variables")
    if spec["goal"] == "diagnose" and variables:
        raise EvidenceError("diagnose cannot retune the original supplied design")
    for name, variable in variables.items():
        if name not in parameters:
            raise EvidenceError("design variables must name declared parameters")
        fields(variable, {"minimum", "maximum", "source"}, "design variable")
        text(variable.get("source"), "design variable source")
        low, high = (valid_value(name, variable.get(key)) for key in ("minimum", "maximum"))
        value = valid_value(name, choices[name])
        if not low <= value <= high:
            raise EvidenceError("common design choice exceeds original variable bounds")
        nominal[name] = value
    axes = spec.get("axes")
    if not isinstance(axes, list) or not 1 <= len(axes) <= 8:
        raise EvidenceError("axes: declare 1-8 independent component tolerance dimensions")
    dimensions, axis_ids, varied = [], [], set()
    for axis in axes:
        fields(axis, {"id", "parameter", "unit", "source", "factors"}, "tolerance axis")
        axis_ids.append(identifier(axis.get("id")))
        parameter = axis.get("parameter")
        if not isinstance(parameter, str) or parameter not in parameters or parameter in varied:
            raise EvidenceError("tolerance axes must target distinct declared parameters")
        if axis.get("unit") != "1":
            raise EvidenceError("relative tolerance factors are dimensionless")
        text(axis.get("source"), "tolerance source")
        factors = axis.get("factors")
        if not isinstance(factors, list) or not 2 <= len(factors) <= 8:
            raise EvidenceError("each tolerance axis needs 2-8 distinct positive factors")
        samples = []
        for factor in factors:
            positive(factor, "tolerance factor")
            try:
                value = float(Fraction(str(nominal[parameter])) * Fraction(str(factor)))
            except OverflowError as exc:
                raise EvidenceError("tolerance product exceeds finite component range") from exc
            samples.append((factor, valid_value(parameter, value)))
        if len({value for _, value in samples}) != len(samples):
            raise EvidenceError("tolerance samples must remain distinct after resolution")
        dimensions.append((axis["id"], parameter, samples))
        varied.add(parameter)
    names(axis_ids, "tolerance axis ids")
    grid_size = math.prod(len(samples) for _, _, samples in dimensions)
    if grid_size > MAX_SCENARIOS:
        raise EvidenceError("Cartesian tolerance grid exceeds 17 scenarios; no corners were dropped")
    scenarios = [{"id": "nominal", "coordinates": {}, "parameters": nominal}]
    for index, point in enumerate(itertools.product(*(values for _, _, values in dimensions))):
        values = {**nominal, **{parameter: pair[1] for (_, parameter, _), pair in zip(dimensions, point)}}
        if values == nominal:
            continue
        scenarios.append({
            "id": f"corner_{index:03d}", "parameters": values,
            "coordinates": {identity: pair[0] for (identity, _, _), pair in zip(dimensions, point)},
        })
    if len(scenarios) > MAX_SCENARIOS:
        raise EvidenceError("Cartesian grid plus nominal exceeds 17 scenarios")
    for study in studies:
        if len(study["checks"]) > 32:
            raise EvidenceError("robustness studies support at most 32 checks")
        frequencies = networks[study["network"]].f
        for check in study["checks"]:
            fields(check, CHECK_FIELDS, "check")
            expected_unit = {"s_db": "dB", "s_phase_deg": "deg"}.get(check["metric"], "1")
            if check["unit"] != expected_unit:
                raise EvidenceError("check unit does not match its RF metric")
            positions = [check["at_hz"]] if check["statistic"] == "at" else check["window_hz"]
            if any(position not in frequencies for position in positions):
                raise EvidenceError("robustness check positions must be explicit original frequency samples")
            lower, upper = (number(check.get(key, 0), key) for key in ("margin_lower", "margin_upper"))
            span = check["maximum"] - check["minimum"]
            exact_span = Fraction(str(check["maximum"])) - Fraction(str(check["minimum"]))
            if not math.isfinite(span) or Fraction(str(lower))+Fraction(str(upper)) > exact_span:
                raise EvidenceError("required margins do not fit inside original bounds")
            number(check.get("max_delta"), "frequency refinement max_delta")
    entries = len(scenarios) * sum((3*len(network.f)-1)*network.nports**2 for network in networks.values())
    if entries > MAX_SCATTERING_ENTRIES:
        raise EvidenceError("complete refined study exceeds 2000000 scattering entries")
    return Study(spec, choices, tuple(sorted(inputs)), definitions, tuple(scenarios), grid_size)


def rendered_networks(study: Study, scenario: dict, resolution: str) -> dict:
    definitions = copy.deepcopy(study.definitions)
    for name, definition in study.specification["parameters"].items():
        definitions[definition["network"]]["elements"][definition["element"]-1]["value_si"] = scenario["parameters"][name]
    if resolution == "fine":
        for node in definitions.values():
            if node["kind"] in ("lumped", "line"):
                node["frequency_hz"] = refined_grid(node["frequency_hz"])
    return definitions


def model_bytes(definitions: dict) -> bytes:
    return (json.dumps(definitions, indent=2) + "\n").encode("utf-8")
