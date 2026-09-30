"""Resolve original parameter samples and explicit numerical refinements."""
from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    names,
    number,
    project_file,
    record,
)

from .evidence import (
    PLAN,
    RESULTS_DIR,
    _identifier,
    _text,
    _validate_check,
    deck_inputs,
    validate_model,
)

MAX_SCENARIOS = 17
MAX_ESTIMATED_POINTS = 1_500_000
MAX_INPUT_BYTES = 4 * 1024 * 1024
UNITS = {"V", "A", "ohm", "F", "H", "Hz", "s", "1", "degC"}
_LITERAL = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_PARAM = re.compile(rf"\.param\s+([a-z][a-z0-9_]*)\s*=\s*({_LITERAL}[a-z]*)", re.I)
_SCALES = {"": 0, "t": 12, "g": 9, "meg": 6, "k": 3, "m": -3,
           "u": -6, "n": -9, "p": -12, "f": -15}
CHECK_FIELDS = {
    "id", "requirement", "vector", "denominator", "component", "statistic", "unit",
    "minimum", "maximum", "at", "window", "level", "direction",
    "margin_lower", "margin_upper", "max_delta",
}


def fields(value: object, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise EvidenceError(f"{label}: expected an object with only {sorted(allowed)}")
    return value


def spice_number(text: str) -> float:
    match = re.fullmatch(rf"({_LITERAL})([a-z]*)", text, re.I)
    if match is None or match[2].lower() not in _SCALES:
        raise EvidenceError(f"expected a literal SPICE number, got {text!r}")
    mantissa, _, exponent = match[1].lower().partition("e")
    try:
        value = float(f"{mantissa}e{int(exponent or '0') + _SCALES[match[2].lower()]}")
    except ValueError as exc:
        raise EvidenceError(f"invalid literal SPICE number: {text!r}") from exc
    return number(value, "SPICE value", minimum=-math.inf)


def _line(text: str) -> str:
    return text.split("$", 1)[0].strip()


def parameter_values(text: str) -> dict[str, float]:
    values = {}
    for line in text.splitlines():
        line = _line(line)
        if not line or line.startswith("*"):
            continue
        match = _PARAM.fullmatch(line)
        if match is None:
            raise EvidenceError("parameter file needs one literal .param name=value per line")
        name = _identifier(match[1], "parameter")
        if name in values:
            raise EvidenceError(f"duplicate parameter {name}")
        values[name] = spice_number(match[2])
    if not values:
        raise EvidenceError("parameter file is empty")
    return values


def analysis_grid(text: str, kind: str, *, fine: bool) -> tuple[str, int]:
    lines = [_line(line) for line in text.splitlines()[1:]]
    selected = [line for line in lines if line.lower().split()[:1] == [f".{kind}"]]
    if len(selected) != 1 or sum(line.lower() == ".end" for line in lines) != 1:
        raise EvidenceError("each top-level deck needs its analysis on one line and one .end")
    tokens = selected[0].split()
    factor = 2 if fine else 1
    if kind == "op" and len(tokens) == 1:
        return ".op", 1
    if kind == "ac" and len(tokens) == 5 and tokens[1].lower() in {"lin", "dec", "oct"}:
        scale = tokens[1].lower()
        if not re.fullmatch(r"[0-9]{1,6}", tokens[2]) or not 2 <= int(tokens[2]) <= 100_000:
            raise EvidenceError("AC sweep needs an integer density/count in 2..100000")
        count = int(tokens[2])
        start, stop = map(spice_number, tokens[3:])
        if not 0 < start < stop:
            raise EvidenceError("AC sweep requires 0 < start < stop")
        count = (count - 1) * factor + 1 if scale == "lin" else count * factor
        base = 10 if scale == "dec" else 2
        points = count if scale == "lin" else math.ceil((math.log(stop, base)-math.log(start, base)) * count) + 1
        directive = f".ac {scale} {count} {start:.17g} {stop:.17g}"
    elif kind == "dc" and len(tokens) == 5 and re.fullmatch(r"[vi][a-z0-9_]+", tokens[1], re.I):
        start, stop, step = map(spice_number, tokens[2:])
        if step/factor == 0 or (stop-start)/step <= 0:
            raise EvidenceError("DC step must follow the direction of a nonempty sweep")
        intervals = number((stop-start)/step, "DC grid length")
        if not math.isclose(intervals, round(intervals), rel_tol=1e-10, abs_tol=1e-10):
            raise EvidenceError("DC endpoints must span an integer number of steps")
        points = round(intervals) * factor + 1
        directive = f".dc {tokens[1]} {start:.17g} {stop:.17g} {step/factor:.17g}"
    elif kind == "tran":
        uic = tokens[-1].lower() == "uic"
        values = tokens[1:-1] if uic else tokens[1:]
        if len(values) != 4:
            raise EvidenceError("transient refinement requires .tran tstep tstop tstart tmax [uic]")
        step, stop, start, maximum = map(spice_number, values)
        if not 0 <= start < stop or step/factor <= 0 or maximum/factor <= 0:
            raise EvidenceError("invalid transient time range or maximum step")
        points = math.ceil(number(stop / min(step, maximum) * factor, "transient grid length")) + 32
        directive = f".tran {step/factor:.17g} {stop:.17g} {start:.17g} {maximum/factor:.17g}" + (" uic" if uic else "")
    else:
        raise EvidenceError("supported refinements are OP, single-source DC, AC lin/dec/oct and explicit four-value transient")
    if not 2 <= points <= 100_000:
        raise EvidenceError("refined analysis exceeds the 100000-point estimate or has too few samples")
    return directive, points


@dataclass(frozen=True)
class Case:
    id: str
    scenario: str
    parameters: dict[str, float]
    analysis: dict
    resolution: str
    directive: str
    reltol: float
    estimated_points: int


@dataclass(frozen=True)
class Study:
    specification: dict
    choices: dict
    inputs: tuple[str, ...]
    model_files: tuple[str, ...]
    scenarios: tuple[dict, ...]
    cases: tuple[Case, ...]
    grid_size: int


def resolve_study(root: Path) -> Study:
    root = root.resolve()
    plan = validate_model(root)
    if len(plan["models"]) > 32:
        raise EvidenceError("robustness scope supports at most 32 original model/deck files")
    if "runs" in plan:
        raise EvidenceError("robustness mode must not also declare legacy runs")
    fields(plan, {"objective", "requirements", "limitations", "models", "robustness"}, "robustness plan")
    selected = fields(plan.get("robustness"), {"specification", "design"}, "robustness")
    relative = _text(selected.get("specification"), "operating specification")
    inputs = {PLAN, relative, *plan["models"]}
    total_bytes = 0
    for path in inputs:
        if Path(path).as_posix() != path or path.startswith(RESULTS_DIR + "/"):
            raise EvidenceError("original input paths must be canonical and outside results")
        total_bytes += project_file(root, path).stat().st_size
        if total_bytes > MAX_INPUT_BYTES:
            raise EvidenceError("original inputs exceed 4 MiB")
    spec = fields(record(root, relative), {
        "goal", "source", "limitations", "parameter_file", "parameters",
        "design_variables", "axes", "analyses", "relative_tolerances",
    }, "operating specification")
    if spec.get("goal") not in ("diagnose", "design"):
        raise EvidenceError("goal must be diagnose or design")
    _text(spec.get("source"), "specification source")
    names(spec.get("limitations"), "specification limitations")
    parameter_file = _text(spec.get("parameter_file"), "parameter file")
    if parameter_file not in plan["models"]:
        raise EvidenceError("parameter file needs model provenance")
    original = parameter_values(project_file(root, parameter_file).read_text())
    parameters = spec.get("parameters")
    if not isinstance(parameters, dict) or set(parameters) != set(original):
        raise EvidenceError("parameters must describe every original literal parameter exactly")

    def valid_value(name: str, value: object) -> float:
        definition = parameters[name]
        value = number(value, name, minimum=-math.inf)
        if not definition["minimum"] <= value <= definition["maximum"]:
            raise EvidenceError(f"{name}: sample or design lies outside declared model validity")
        return value

    for name, definition in parameters.items():
        fields(definition, {"nominal", "minimum", "maximum", "unit", "source"}, f"parameter {name}")
        if not isinstance(definition.get("unit"), str) or definition["unit"] not in UNITS:
            raise EvidenceError(f"{name}: declare a supported SI unit or degC")
        _text(definition.get("source"), f"{name} source")
        low = number(definition.get("minimum"), f"{name} minimum", minimum=-math.inf)
        high = number(definition.get("maximum"), f"{name} maximum", minimum=-math.inf)
        if low > high or (definition["unit"] == "degC" and low <= -273.15):
            raise EvidenceError(f"{name}: invalid model-validity range")
        if valid_value(name, definition.get("nominal")) != original[name]:
            raise EvidenceError(f"{name}: nominal specification differs from the original parameter file")
    choices, variables = selected.get("design"), spec.get("design_variables")
    if not isinstance(choices, dict) or not isinstance(variables, dict) or set(choices) != set(variables):
        raise EvidenceError("design must select exactly the declared common variables")
    if spec["goal"] == "diagnose" and variables:
        raise EvidenceError("diagnose fixes the supplied design; it cannot declare design variables")
    nominal, chosen = dict(original), set()
    for name, variable in variables.items():
        _identifier(name, "design variable")
        fields(variable, {"parameter", "minimum", "maximum", "source"}, "design variable")
        parameter = variable.get("parameter")
        if not isinstance(parameter, str) or parameter not in parameters or parameter in chosen:
            raise EvidenceError("design variables need distinct declared parameters")
        _text(variable.get("source"), "design source")
        low = number(variable.get("minimum"), "design minimum", minimum=-math.inf)
        high = number(variable.get("maximum"), "design maximum", minimum=-math.inf)
        value = valid_value(parameter, choices[name])
        if not low <= value <= high:
            raise EvidenceError("design choice exceeds original variable bounds")
        nominal[parameter] = value
        chosen.add(parameter)
    axes = spec.get("axes")
    if not isinstance(axes, list) or not 1 <= len(axes) <= 8:
        raise EvidenceError("axes: declare 1-8 parameter dimensions")
    dimensions, targets, axis_ids = [], set(), []
    for axis in axes:
        fields(axis, {"id", "parameter", "unit", "source", "values", "factors"}, "axis")
        axis_ids.append(_identifier(axis.get("id"), "axis id"))
        parameter = axis.get("parameter")
        if not isinstance(parameter, str) or parameter not in parameters or parameter in targets:
            raise EvidenceError("axes need distinct declared parameters")
        factor = "factors" in axis
        if factor == ("values" in axis):
            raise EvidenceError("axis needs either absolute values or relative factors")
        if axis.get("unit") != ("1" if factor else parameters[parameter]["unit"]):
            raise EvidenceError("axis unit differs from its parameter or dimensionless factor")
        _text(axis.get("source"), "axis source")
        if not factor and parameter in chosen:
            raise EvidenceError("absolute axis must not replace a selected design variable")
        if factor and (nominal[parameter] <= 0 or parameters[parameter]["unit"] == "degC"):
            raise EvidenceError("factors need a positive non-temperature nominal value")
        values = axis["factors" if factor else "values"]
        if not isinstance(values, list) or not 2 <= len(values) <= 8:
            raise EvidenceError("each axis needs 2-8 distinct finite samples")
        resolved = []
        for value in values:
            value = number(value, "axis value", minimum=0 if factor else -math.inf)
            if factor and value == 0:
                raise EvidenceError("relative factors must be positive")
            if factor:
                # Two shortest binary64 decimal representations need at most 34 product digits.
                with localcontext(prec=34):
                    value = float(Decimal(str(nominal[parameter])) * Decimal(str(value)))
            resolved.append(valid_value(parameter, value))
        if len(set(resolved)) != len(resolved):
            raise EvidenceError("resolved axis values must remain distinct")
        dimensions.append((axis["id"], parameter, resolved))
        targets.add(parameter)
    names(axis_ids, "axis ids")
    grid_size = math.prod(len(values) for _, _, values in dimensions)
    if grid_size > MAX_SCENARIOS:
        raise EvidenceError("Cartesian grid exceeds the 17-scenario limit; no combinations were dropped")
    scenarios = [{"id": "nominal", "coordinates": {}, "parameters": nominal}]
    for index, point in enumerate(itertools.product(*(values for _, _, values in dimensions))):
        values = {**nominal, **{parameter: v for (_, parameter, _), v in zip(dimensions, point)}}
        if values == nominal:
            continue
        scenarios.append({"id": f"corner_{index:03d}", "parameters": values,
                          "coordinates": {identity: v for (identity, _, _), v in zip(dimensions, point)}})
    if len(scenarios) > MAX_SCENARIOS:
        raise EvidenceError("Cartesian samples plus nominal exceed 17 scenarios")
    tolerances = spec.get("relative_tolerances")
    if not isinstance(tolerances, list) or len(tolerances) != 2:
        raise EvidenceError("declare coarse/fine relative_tolerances")
    coarse, fine = (number(v, "relative tolerance") for v in tolerances)
    if not 1e-12 <= fine <= coarse/10 or coarse > 1e-2:
        raise EvidenceError("fine reltol must be >=1e-12 and at most coarse/10; coarse <=1e-2")
    analyses = spec.get("analyses")
    if not isinstance(analyses, list) or not 1 <= len(analyses) <= 4:
        raise EvidenceError("analyses: declare 1-4 required methods")
    covered, analysis_ids, grids = set(), [], {}
    for analysis in analyses:
        fields(analysis, {"id", "kind", "netlist", "checks"}, "analysis")
        identity = _identifier(analysis.get("id"), "analysis id")
        analysis_ids.append(identity)
        kind = analysis.get("kind")
        if kind not in ("op", "dc", "ac", "tran"):
            raise EvidenceError("analysis kind must be op, dc, ac or tran")
        netlist = _text(analysis.get("netlist"), "analysis netlist")
        dependencies, methods = deck_inputs(
            root, netlist, declared_files=set(plan["models"]), max_expanded_bytes=MAX_INPUT_BYTES,
        )
        if methods != [kind] or not dependencies <= plan["models"].keys() or parameter_file not in dependencies:
            raise EvidenceError("each declared deck must include the parameter file and exactly its declared analysis")
        text = project_file(root, netlist).read_text()
        grids[identity] = [analysis_grid(text, kind, fine=fine) for fine in (False, True)]
        checks = analysis.get("checks")
        if not isinstance(checks, list) or not 1 <= len(checks) <= 32:
            raise EvidenceError("each analysis needs 1-32 numerical checks")
        for check in checks:
            fields(check, CHECK_FIELDS, "check")
            covered.add(_validate_check(check, plan["requirements"]))
            if (kind == "op") != (check["statistic"] == "point"):
                raise EvidenceError("use point only for OP and axis statistics for other analyses")
            lower = number(check.get("margin_lower", 0), "lower margin")
            upper = number(check.get("margin_upper", 0), "upper margin")
            number(check.get("max_delta"), "refinement max_delta")
            span = check["maximum"]-check["minimum"]
            if not math.isfinite(span) or lower + upper > span:
                raise EvidenceError("required margins do not fit inside original bounds")
        names([check["id"] for check in checks], "check ids")
    names(analysis_ids, "analysis ids")
    if covered != set(plan["requirements"]):
        raise EvidenceError("every declared requirement must have a numerical check")
    for path in plan["models"]:
        file = project_file(root, path)
        if path != parameter_file:
            for line in file.read_text().splitlines():
                text = _line(line)
                if re.match(r"(?:\.options?\b|\+).*\breltol\s*=", text, re.I):
                    raise EvidenceError("relative_tolerances owns reltol; remove conflicting source options explicitly")
                if re.match(r"(?:\.(?:param|subckt)\b|\+)", text, re.I) and any(
                    re.search(rf"\b{re.escape(name)}\s*=", text, re.I) for name in parameters
                ):
                    raise EvidenceError("sampled parameters must not be redeclared outside their parameter file")
    cases = tuple(
        Case(f"{scenario['id']}_{analysis['id']}_{resolution}", scenario["id"], scenario["parameters"],
             analysis, resolution, grids[analysis["id"]][i][0], tolerances[i], grids[analysis["id"]][i][1])
        for scenario in scenarios for analysis in analyses for i, resolution in enumerate(("coarse", "fine"))
    )
    if sum(case.estimated_points for case in cases) > MAX_ESTIMATED_POINTS:
        raise EvidenceError("complete study exceeds the 1500000-point estimate")
    return Study(spec, choices, tuple(sorted(inputs)), tuple(sorted(plan["models"])), tuple(scenarios), cases, grid_size)


def rendered_inputs(root: Path, study: Study, case: Case) -> dict[str, bytes]:
    files = {path: project_file(root, path).read_bytes() for path in study.model_files}
    files[study.specification["parameter_file"]] = (
        "* Declared common design and finite sample\n"
        + "".join(f".param {name}={value:.17g}\n" for name, value in sorted(case.parameters.items()))
    ).encode("ascii")
    entry = case.analysis["netlist"]
    lines = files[entry].decode("utf-8").splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if _line(line).lower().split()[:1] == ["." + case.analysis["kind"]]:
            lines[index] = case.directive
        elif _line(line).lower() == ".end":
            lines[index] = f".options reltol={case.reltol:.17g}\n.end"
    files[entry] = ("\n".join(lines) + "\n").encode("utf-8")
    return files
