"""Bind analog requirements to native runs and recomputed waveform measurements."""
from __future__ import annotations

import math
import re
import shlex
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    command_result,
    current_files,
    names,
    number,
    project_file,
    record,
)

from .raw import PLOT_NAMES, measure, read_plot

PLAN = "analog/PLAN.json"
RESULTS_DIR = "analog/results"
INPUTS_DIR = RESULTS_DIR + "/inputs"
RESULTS = RESULTS_DIR + "/RESULTS.json"
RUN_ENVIRONMENT = {"SPICE_ASCIIRAWFILE": "1"}
_ID = re.compile(r"[a-z][a-z0-9_]{0,47}")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field}: expected nonempty text")
    return value


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise EvidenceError(f"{field}: use a lowercase underscore identifier")
    return value


def validate_specification(root: Path) -> dict:
    plan = record(root, PLAN)
    _text(plan.get("objective"), "objective")
    names(plan.get("limitations"), "limitations")
    requirements = plan.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise EvidenceError("requirements: map identifiers to observable requirements")
    for key, description in requirements.items():
        _identifier(key, "requirement")
        _text(description, f"requirements.{key}")
    return plan


def validate_model(root: Path) -> dict:
    plan = validate_specification(root)
    models = plan.get("models")
    if not isinstance(models, dict) or not models:
        raise EvidenceError("models: describe each deck and included file")
    for relative, model in models.items():
        project_file(root, relative)
        if not isinstance(model, dict) or model.get("kind") not in ("ideal", "behavioral", "device", "testbench"):
            raise EvidenceError(f"models.{relative}: declare ideal, behavioral, device or testbench")
        _text(model.get("source"), f"models.{relative}.source")
        _text(model.get("validity"), f"models.{relative}.validity")
        names(model.get("limitations"), f"models.{relative}.limitations")
    return plan


def deck_inputs(root: Path, entry: str) -> tuple[set[str], list[str]]:
    files: set[str] = set()
    active: set[str] = set()
    analyses: list[str] = []

    def visit(relative: str, *, top: bool = False) -> None:
        if relative in active:
            raise EvidenceError(f"cyclic SPICE include: {relative}")
        active.add(relative)
        path = project_file(root, relative)
        files.add(relative)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise EvidenceError(f"{relative}: cannot read SPICE input: {exc}") from exc
        if top:
            lines = lines[1:]  # ngspice treats the first deck line as its title.
        for line in lines:
            text = line.strip()
            if not text or text.startswith("*"):
                continue
            if re.search(r"\b(?:file|input_file|output_file)\s*=", text, re.IGNORECASE):
                raise EvidenceError(f"{relative}: file-driven sources/models are not supported by this adapter")
            if not text.startswith("."):
                continue
            try:
                fields = shlex.split(text.split("$", 1)[0])
            except ValueError as exc:
                raise EvidenceError(f"{relative}: invalid directive quoting: {exc}") from exc
            directive = fields[0].lower()
            if directive in {".include", ".inc"}:
                if len(fields) != 2:
                    raise EvidenceError(f"{relative}: .include needs one literal project-relative path")
                visit(fields[1])
            elif directive in {".control", ".lib", ".hdl", ".osdi"}:
                raise EvidenceError(f"{relative}: {directive} is outside this batch adapter")
            elif directive[1:] in PLOT_NAMES:
                analyses.append(directive[1:])
            elif directive in {".noise", ".pz", ".tf", ".disto", ".sens", ".sp", ".pss"}:
                raise EvidenceError(f"{relative}: {directive} analysis is not supported yet")
            elif directive == ".end" and not top:
                raise EvidenceError(f"{relative}: an included fragment must not terminate the deck")
        active.remove(relative)

    visit(entry, top=True)
    return files, analyses


def _validate_check(check: object, requirements: dict) -> str:
    if not isinstance(check, dict):
        raise EvidenceError("checks: each measurement must be an object")
    _identifier(check.get("id"), "check.id")
    requirement = _identifier(check.get("requirement"), "check.requirement")
    if requirement not in requirements:
        raise EvidenceError(f"unknown requirement {requirement}")
    _text(check.get("vector"), "check.vector")
    if "denominator" in check:
        _text(check["denominator"], "check.denominator")
    if check.get("component") not in ("real", "imag", "magnitude", "phase_deg"):
        raise EvidenceError("check.component: choose real, imag, magnitude or phase_deg")
    if check.get("unit") not in ("V", "A", "Hz", "s", "1", "ohm", "S", "deg"):
        raise EvidenceError("check.unit: use a supported SI unit, 1 for dimensionless ratios")
    lower = number(check.get("minimum"), "check.minimum", minimum=-math.inf)
    upper = number(check.get("maximum"), "check.maximum", minimum=-math.inf)
    if lower > upper:
        raise EvidenceError("check.minimum exceeds maximum")
    statistic = check.get("statistic")
    if statistic not in ("point", "at", "min", "max", "crossing"):
        raise EvidenceError("check.statistic: choose point, at, min, max or crossing")
    if statistic == "at":
        number(check.get("at"), "check.at", minimum=-math.inf)
    if statistic in {"min", "max", "crossing"}:
        window = check.get("window")
        if not isinstance(window, list) or len(window) != 2:
            raise EvidenceError("check.window: declare [start, stop] in axis SI units")
        low = number(window[0], "window.start", minimum=-math.inf)
        high = number(window[1], "window.stop", minimum=-math.inf)
        if low >= high:
            raise EvidenceError("check.window: start must be less than stop")
    if statistic == "crossing":
        number(check.get("level"), "check.level", minimum=-math.inf)
        if check.get("direction") not in ("rising", "falling"):
            raise EvidenceError("check.direction: choose rising or falling")
    return requirement


def validate_plan(root: Path) -> tuple[dict, list[str]]:
    if "robustness" in record(root, PLAN):
        from .study import resolve_study

        study = resolve_study(root)
        return record(root, PLAN), list(study.inputs)
    plan = validate_model(root)
    runs = plan.get("runs")
    if not isinstance(runs, list) or not runs:
        raise EvidenceError("runs: declare the requested analyses and numerical acceptance checks")
    ids = []
    inputs = {PLAN, *plan["models"]}
    covered: set[str] = set()
    for run in runs:
        if not isinstance(run, dict):
            raise EvidenceError("runs: each entry must be an object")
        ids.append(_identifier(run.get("id"), "run.id"))
        if not isinstance(run.get("kind"), str) or run["kind"] not in PLOT_NAMES:
            raise EvidenceError("run.kind: choose op, dc, ac or tran")
        netlist = _text(run.get("netlist"), "run.netlist")
        dependencies, analyses = deck_inputs(root, netlist)
        if analyses != [run["kind"]]:
            raise EvidenceError(f"{run['id']}: deck must contain exactly its one declared analysis")
        missing = dependencies - set(plan["models"])
        if missing:
            raise EvidenceError(f"models: missing provenance and validity for {sorted(missing)}")
        inputs.update(dependencies)
        checks = run.get("checks")
        if not isinstance(checks, list) or not checks:
            raise EvidenceError(f"{run['id']}: declare at least one numerical check")
        check_ids = []
        for check in checks:
            covered.add(_validate_check(check, plan["requirements"]))
            check_ids.append(check["id"])
            if (run["kind"] == "op") != (check["statistic"] == "point"):
                raise EvidenceError("use point for op and axis-based measurements for other analyses")
        names(check_ids, "check ids")
    names(ids, "run ids")
    if covered != set(plan["requirements"]):
        raise EvidenceError("every declared requirement must have a numerical check")
    return plan, sorted(inputs)


def run_paths(identity: str) -> dict[str, str]:
    directory = f"{RESULTS_DIR}/runs/{identity}"
    return {
        "raw": f"{directory}/wave.raw",
        "log": f"{directory}/ngspice.log",
        "console": f"{directory}/console.log",
    }


def run_command(run: dict) -> list[str]:
    directory = "../runs/" + run["id"]
    return [
        "ngspice", "-n", "-b", "-r", directory + "/wave.raw",
        "-o", directory + "/ngspice.log", run["netlist"],
    ]


def validate_simulation(root: Path) -> dict:
    if "robustness" in record(root, PLAN):
        from .robustness import validate_robustness

        return validate_robustness(root)
    plan, required = validate_plan(root)
    results = record(root, RESULTS)
    _text(results.get("tool_version"), "tool_version")
    expected_inputs = {relative: f"{INPUTS_DIR}/{relative}" for relative in required}
    if results.get("inputs") != expected_inputs:
        raise EvidenceError("inputs: every declared input must have its corresponding execution-tree copy")
    current_files(root, results, required)
    if results.get("environment") != RUN_ENVIRONMENT:
        raise EvidenceError("environment: record SPICE_ASCIIRAWFILE=1")
    runs = results.get("runs")
    if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
        raise EvidenceError("runs: expected actual ngspice execution records")
    ids = names([run.get("id") for run in runs], "executed run ids")
    planned = {run["id"]: run for run in plan["runs"]}
    if set(ids) != set(planned):
        raise EvidenceError("executed runs must match the requested analyses exactly")
    measurements = {}
    outputs = []
    for run in runs:
        identity = run["id"]
        expected = planned[identity]
        paths = run_paths(identity)
        if run.get("command") != run_command(expected) or run.get("cwd") != INPUTS_DIR:
            raise EvidenceError(f"{identity}: command/cwd differs from the frozen-input batch invocation")
        if any(run.get(key) != value for key, value in paths.items()):
            raise EvidenceError(f"{identity}: output paths do not match the invocation")
        log = command_result(root, run)
        try:
            console = project_file(root, run["console"]).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise EvidenceError(f"{identity}: cannot read native console output: {exc}") from exc
        if re.search(r"(?im)^\s*(?:fatal|error|doAnalyses:|run simulation\(s\) aborted)", log + "\n" + console):
            raise EvidenceError(f"{identity}: native simulator output contains a failure")
        plot = read_plot(project_file(root, run["raw"]), expected["kind"])
        reported_rows = re.findall(r"No\. of Data Rows\s*:\s*(\d+)", log)
        if reported_rows != [str(len(plot.rows))]:
            raise EvidenceError(f"{identity}: native log and waveform point counts disagree")
        values = {}
        for check in expected["checks"]:
            value, unit = measure(plot, check)
            if unit != check["unit"]:
                raise EvidenceError(f"{identity}/{check['id']}: measured {unit}, not declared {check['unit']}")
            if not math.isfinite(value) or not check["minimum"] <= value <= check["maximum"]:
                raise EvidenceError(
                    f"{identity}/{check['id']}: {value:g} {unit} outside "
                    f"[{check['minimum']:g}, {check['maximum']:g}]"
                )
            values[check["id"]] = value
        measurements[identity] = values
        outputs.extend(paths.values())
    current_files(root, results, outputs, field="outputs")
    return measurements
