"""Standalone analog ngspice runner and evidence check, adapted from the Argus analog_mixed_signal vertical.

One standard-library file holding the analog plan/model/simulation checks, the operating-envelope
study, the native ASCII raw reader and the bounded ngspice batch runner. Accepted envelope checks
are not cached anywhere: every check of an envelope study replays all native cases.
"""
from __future__ import annotations

import argparse
import bisect
import cmath
import itertools
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from signal import SIGKILL
from typing import TextIO


# Common file, numeric and command-record checks.


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


def command_result(root: Path, run: dict) -> str:
    command = run.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise EvidenceError("command: expected the actual argument vector")
    if type(run.get("exit_code")) is not int or run["exit_code"] != 0:
        raise EvidenceError("command did not exit successfully")
    try:
        return project_file(root, run.get("log")).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"cannot read command output: {exc}") from exc


# Native ASCII ngspice reader and scalar waveform measurements.

PLOT_NAMES = {
    "op": "Operating Point",
    "dc": "DC transfer characteristic",
    "ac": "AC Analysis",
    "tran": "Transient Analysis",
}
SIGNAL_UNITS = {"voltage": "V", "current": "A", "time": "s", "frequency": "Hz"}
MAX_RAW_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class Plot:
    kind: str
    variables: tuple[tuple[str, str], ...]
    rows: tuple[tuple[complex, ...], ...]

    def signal(self, name: str) -> tuple[list[complex], str]:
        for index, (vector, quantity) in enumerate(self.variables):
            if vector == name.lower():
                if self.kind != "op" and index == 0:
                    raise EvidenceError("measure a signal, not the independent sweep axis")
                if quantity not in SIGNAL_UNITS:
                    raise EvidenceError(f"unsupported signal quantity: {quantity}")
                return [row[index] for row in self.rows], SIGNAL_UNITS[quantity]
        raise EvidenceError(f"native output does not contain vector {name!r}; check .save")


def read_plot(path: Path, kind: str) -> Plot:
    if not isinstance(kind, str) or kind not in PLOT_NAMES:
        raise EvidenceError("unsupported native analysis kind")
    try:
        if path.stat().st_size > MAX_RAW_BYTES:
            raise ValueError("native waveform exceeds the 64 MiB reader limit")
        lines = iter(path.read_text(encoding="ascii").splitlines())
        header = {}
        for line in lines:
            if line.strip() == "Variables:":
                break
            key, value = line.split(":", 1)
            if key in header:
                raise ValueError(f"duplicate header {key}")
            header[key] = value.strip()
        if header.get("Plotname") != PLOT_NAMES[kind]:
            raise ValueError("native plot does not match the requested analysis")
        flags = "complex" if kind == "ac" else "real"
        if header.get("Flags") != flags:
            raise ValueError(f"expected {flags} native values")
        nvars, npoints = int(header["No. Variables"]), int(header["No. Points"])
        if not 1 <= nvars <= 128 or not 1 <= npoints <= 100_000:
            raise ValueError("expected 1-128 vectors and 1-100000 points")
        variables = []
        for index in range(nvars):
            fields = next(lines).split()
            if len(fields) < 3 or fields[0] != str(index):
                raise ValueError("invalid native variable index")
            variables.append((fields[1].lower(), fields[2].lower()))
        if len({name for name, _ in variables}) != nvars:
            raise ValueError("duplicate native vectors")
        if next(lines).strip() != "Values:":
            raise ValueError("expected ASCII Values; use the supplied batch runner")
        rows = []
        for point in range(npoints):
            row = []
            for index in range(nvars):
                value = next(lines).strip()
                if index == 0:
                    ordinal, value = value.split(None, 1)
                    if ordinal != str(point):
                        raise ValueError("invalid native point index")
                pieces = value.split(",")
                if len(pieces) != (2 if flags == "complex" else 1):
                    raise ValueError("wrong number of real/imaginary components")
                parsed = complex(float(pieces[0]), float(pieces[1]) if flags == "complex" else 0)
                if kind == "ac" and index == 0:
                    # ngspice 42 may leave the unused frequency imaginary slot uninitialized.
                    parsed = complex(parsed.real)
                if not math.isfinite(parsed.real) or not math.isfinite(parsed.imag):
                    raise ValueError("nonfinite native signal")
                row.append(parsed)
            rows.append(tuple(row))
        if any(line.strip() for line in lines):
            raise ValueError("extra data or multiple plots; use one analysis per deck")
        if kind == "op":
            if npoints != 1:
                raise ValueError("operating point must contain exactly one point")
        else:
            expected_axis = {"ac": {"frequency"}, "tran": {"time"}, "dc": {"voltage", "current"}}[kind]
            if variables[0][1] not in expected_axis or npoints < 2:
                raise ValueError("invalid independent axis or insufficient points")
            axis = [row[0].real for row in rows]
            if kind in {"ac", "tran"} and min(axis) < 0:
                raise ValueError("negative frequency or time")
            if kind == "dc" and all(a > b for a, b in zip(axis, axis[1:])):
                rows.reverse()
                axis.reverse()
            if any(a >= b for a, b in zip(axis, axis[1:])):
                raise ValueError("expected a strictly increasing one-dimensional axis")
        return Plot(kind, tuple(variables), tuple(rows))
    except (OSError, UnicodeError, ValueError, KeyError, StopIteration) as exc:
        raise EvidenceError(f"{path.name}: invalid native ngspice output: {exc}") from exc


def _interpolate(axis: list[float], values: list[float], position: float) -> float:
    if not axis[0] <= position <= axis[-1]:
        raise EvidenceError(f"measurement position {position} lies outside the saved axis")
    index = bisect.bisect_left(axis, position)
    if axis[index] == position:
        return values[index]
    weight = (position - axis[index - 1]) / (axis[index] - axis[index - 1])
    return values[index - 1] + weight * (values[index] - values[index - 1])


def measure(plot: Plot, check: dict) -> tuple[float, str]:
    signal, unit = plot.signal(check["vector"])
    if check.get("denominator"):
        denominator, other_unit = plot.signal(check["denominator"])
        if any(value == 0 for value in denominator):
            raise EvidenceError("signal ratio has a zero denominator in the saved range")
        signal = [a / b for a, b in zip(signal, denominator)]
        ratio_units = {("V", "V"): "1", ("A", "A"): "1", ("V", "A"): "ohm", ("A", "V"): "S"}
        if (unit, other_unit) not in ratio_units:
            raise EvidenceError("unsupported ratio dimensions")
        unit = ratio_units[unit, other_unit]
    if any(not math.isfinite(value.real) or not math.isfinite(value.imag) for value in signal):
        raise EvidenceError("nonfinite computed signal")
    component = check["component"]
    if component == "magnitude":
        values = [abs(value) for value in signal]
    elif component == "phase_deg":
        if any(value == 0 for value in signal):
            raise EvidenceError("phase is undefined for a zero signal")
        values = []
        for value in signal:
            phase = math.degrees(cmath.phase(value))
            if values:
                phase = values[-1] + (phase - values[-1] + 180) % 360 - 180
            values.append(phase)
        unit = "deg"
    else:
        values = [value.real if component == "real" else value.imag for value in signal]
    if any(not math.isfinite(value) for value in values):
        raise EvidenceError("nonfinite computed signal")
    statistic = check["statistic"]
    if statistic == "point":
        if plot.kind != "op":
            raise EvidenceError("point measurement requires an operating-point analysis")
        return values[0], unit
    if plot.kind == "op":
        raise EvidenceError("operating-point checks use statistic=point")
    axis = [row[0].real for row in plot.rows]
    if statistic == "at":
        return _interpolate(axis, values, check["at"]), unit
    low, high = check["window"]
    positions = [low, *(x for x in axis if low < x < high), high]
    samples = [_interpolate(axis, values, x) for x in positions]
    if statistic in {"min", "max"}:
        return (min(samples) if statistic == "min" else max(samples)), unit
    level = check["level"]
    crossings = []
    touches = {
        index for index in range(1, len(samples) - 1)
        if samples[index] == level
        and (samples[index - 1] < level) == (samples[index + 1] < level)
    }
    for index, (x0, x1, y0, y1) in enumerate(zip(positions, positions[1:], samples, samples[1:])):
        if y0 == level and y1 == level:
            raise EvidenceError("crossing is a plateau, not a unique event")
        if index in touches or index + 1 in touches:
            continue
        if y0 == y1:
            continue
        if check["direction"] == "rising" and y1 < y0:
            continue
        if check["direction"] == "falling" and y1 > y0:
            continue
        if min(y0, y1) <= level <= max(y0, y1):
            value = x0 + (level - y0) * (x1 - x0) / (y1 - y0)
            if not crossings or not math.isclose(value, crossings[-1], rel_tol=1e-12, abs_tol=0):
                crossings.append(value)
    if len(crossings) != 1:
        raise EvidenceError(f"expected one crossing in the declared window, found {len(crossings)}")
    return crossings[0], SIGNAL_UNITS[plot.variables[0][1]]


# Bounded native ngspice batch execution.


def run_monitored(
    command: list[str], *, root: Path, stream: TextIO,
    deadline: float, limit: Callable[[float], str], env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    stopped = ""
    with subprocess.Popen(
        command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            while process.poll() is None:
                if stopped := limit(deadline):
                    break
                with suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=0.05)  # wake as soon as ngspice exits
        finally:
            finished = process.poll() is not None
            if os.name == "posix":
                try:
                    os.killpg(process.pid, SIGKILL)
                    if finished and not stopped:
                        stopped = "native command left owned child processes running"
                except ProcessLookupError:
                    pass
            elif not finished:
                process.kill()
            exit_code = process.wait()
    return exit_code, stopped or limit(deadline)


def ngspice_version() -> str:
    try:
        result = subprocess.run(["ngspice", "-n", "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"native ngspice is required: {exc}") from exc
    match = re.search(r"\bngspice-(\d+(?:\.\d+)?)\b", result.stdout + result.stderr)
    if result.returncode != 0 or match is None or int(match[1].split(".")[0]) < 42:
        raise EvidenceError("this adapter requires native ngspice >=42")
    return match[1]


def run_batch(command: list[str], cwd: Path, output: Path, files: tuple[str, ...], *,
              timeout: float, output_budget: int, save=None) -> dict:
    home = output / "config"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SPICE", "NGSPICE"))}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home), SPICE_ASCIIRAWFILE="1", LC_ALL="C", OMP_NUM_THREADS="1")
    row = {"command": command, "cwd": str(cwd), "log": str(output / "ngspice.log"), "exit_code": None}
    if save:
        save(row)

    def limit(deadline: float) -> str:
        if time.monotonic() >= deadline:
            return f"native simulation exceeded {timeout:g} seconds"
        if sum((output / name).stat().st_size for name in files if (output / name).exists()) > output_budget:
            return f"native output exceeded {output_budget} bytes"
        return ""

    try:
        with (output / "console.log").open("w") as console:
            row["exit_code"], stopped = run_monitored(
                command, root=cwd, stream=console, env=env,
                deadline=time.monotonic() + timeout, limit=limit,
            )
    except OSError as exc:
        raise EvidenceError(f"ngspice execution failed: {exc}") from exc
    if save:
        save(row)
    if stopped or row["exit_code"] != 0:
        raise EvidenceError(f"{stopped or 'ngspice failed'}; inspect {output}")
    return row


# Analog plan, model and per-run simulation records.

PLAN = "analog/PLAN.json"
REVIEW = "analog/REVIEW.md"
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


def deck_inputs(root: Path, entry: str, *, declared_files: set[str] | None = None,
                max_expanded_bytes: int | None = None) -> tuple[set[str], list[str]]:
    files: set[str] = set()
    active: set[str] = set()
    parsed: dict[str, tuple[tuple[str, ...], int]] = {}

    def visit(relative: str, *, top: bool = False) -> tuple[tuple[str, ...], int]:
        if relative in active:
            raise EvidenceError(f"cyclic SPICE include: {relative}")
        if declared_files is not None and relative not in declared_files:
            raise EvidenceError(f"models: missing provenance and validity for {relative}")
        if relative in parsed:
            return parsed[relative]
        active.add(relative)
        path = project_file(root, relative)
        files.add(relative)
        expanded_bytes = path.stat().st_size
        if max_expanded_bytes is not None and expanded_bytes > max_expanded_bytes:
            raise EvidenceError(f"expanded SPICE inputs exceed {max_expanded_bytes} bytes")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise EvidenceError(f"{relative}: cannot read SPICE input: {exc}") from exc
        if top:
            lines = lines[1:]  # ngspice treats the first deck line as its title.
        analyses: list[str] = []
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
                included_analyses, included_bytes = visit(fields[1])
                expanded_bytes += included_bytes
                if max_expanded_bytes is not None and expanded_bytes > max_expanded_bytes:
                    raise EvidenceError(f"expanded SPICE inputs exceed {max_expanded_bytes} bytes")
                analyses.extend(included_analyses)
            elif directive in {".control", ".lib", ".hdl", ".osdi"}:
                raise EvidenceError(f"{relative}: {directive} is outside this batch adapter")
            elif directive[1:] in PLOT_NAMES:
                analyses.append(directive[1:])
            elif directive in {".noise", ".pz", ".tf", ".disto", ".sens", ".sp", ".pss"}:
                raise EvidenceError(f"{relative}: {directive} analysis is not supported yet")
            elif directive == ".end" and not top:
                raise EvidenceError(f"{relative}: an included fragment must not terminate the deck")
        active.remove(relative)
        parsed[relative] = (tuple(analyses), expanded_bytes)
        return parsed[relative]

    analyses, _ = visit(entry, top=True)
    return files, list(analyses)


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


# Operating-envelope study: original parameter samples and explicit numerical refinements.

MAX_SCENARIOS = 17
MAX_ESTIMATED_POINTS = 1_500_000
MAX_INPUT_BYTES = 4 * 1024 * 1024
PARAMETER_UNITS = {"V", "A", "ohm", "F", "H", "Hz", "s", "1", "degC"}
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
        if not isinstance(definition.get("unit"), str) or definition["unit"] not in PARAMETER_UNITS:
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
                base_decimal = Decimal(str(nominal[parameter]))
                factor_decimal = Decimal(str(value))
                # Integer operands can exceed the digits in a binary64 round-trip representation.
                with localcontext() as context:
                    context.prec = len(base_decimal.as_tuple().digits) + len(factor_decimal.as_tuple().digits)
                    value = float(base_decimal * factor_decimal)
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


# Execute full parameter studies and independently assess every sampled result.

ASSESSMENT = RESULTS_DIR + "/ASSESSMENT.json"
FILES = ("wave.raw", "ngspice.log", "console.log")
MAX_STUDY_SECONDS = 600
MAX_STUDY_OUTPUT_BYTES = 512 * 1024 * 1024
SCOPE = "Finite declared parameter samples and numerical sensitivity checks; no continuous-range, statistical or physical qualification."


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EvidenceError("analog study exceeded its aggregate time budget")
    return remaining


def _command(case: Case) -> list[str]:
    return ["ngspice", "-n", "-b", "-r", "../wave.raw", "-o", "../ngspice.log", case.analysis["netlist"]]


def _files(study: Study) -> tuple[str, ...]:
    return (*FILES, *(f"inputs/{path}" for path in study.model_files))


def _outputs(study: Study) -> dict[str, str]:
    return {
        f"{RESULTS_DIR}/native/{case.id}/{path}": f"{RESULTS_DIR}/retained/{case.id}/{path}"
        for case in study.cases for path in _files(study)
    }


def _describe(study: Study) -> list[dict]:
    return [
        {"id": case.id, "scenario": case.scenario, "analysis": case.analysis["id"],
         "parameters": case.parameters, "resolution": case.resolution,
         "directive": case.directive, "reltol": case.reltol}
        for case in study.cases
    ]


def _execute(root: Path, study: Study, case: Case, output: Path, *, deadline: float,
             remaining_bytes: int = MAX_RAW_BYTES, save=None) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    for relative, content in rendered_inputs(root, study, case).items():
        path = output / "inputs" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return run_batch(
        _command(case), output / "inputs", output, _files(study),
        timeout=min(120, _remaining(deadline)),
        output_budget=min(MAX_RAW_BYTES, remaining_bytes), save=save,
    )


def _plot(root: Path, study: Study, case: Case, output: Path) -> Plot:
    for relative, content in rendered_inputs(root, study, case).items():
        if (output / "inputs" / relative).read_bytes() != content:
            raise EvidenceError(f"{case.id}: generated circuit differs from original inputs and declared sample")
    for name in FILES:
        path = output / name
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_RAW_BYTES:
            raise EvidenceError(f"{case.id}: missing, empty or oversized {name}")
    log = (output / "ngspice.log").read_text() + "\n" + (output / "console.log").read_text()
    if re.search(r"(?im)^\s*(?:fatal|error|warning|doAnalyses:|run simulation\(s\) aborted)", log):
        raise EvidenceError(f"{case.id}: native diagnostic requires investigation")
    plot = read_plot(output / "wave.raw", case.analysis["kind"])
    if re.findall(r"No\. of Data Rows\s*:\s*(\d+)", log) != [str(len(plot.rows))]:
        raise EvidenceError(f"{case.id}: native completion count disagrees with waveform")
    return plot


def _collect(root: Path, study: Study, *, replay: bool) -> dict:
    result = record(root, RESULTS)
    if result.get("operation") != "ngspice-analog-corners" or result.get("execution_complete") is not True:
        raise EvidenceError("analog operating-envelope execution is incomplete")
    if result.get("ngspice_version") != ngspice_version():
        raise EvidenceError("installed ngspice differs from the execution record")
    if result.get("cases") != _describe(study) or result.get("goal") != study.specification["goal"]:
        raise EvidenceError("recorded cases or goal differ from the full original study")
    if result.get("inputs") != {path: f"{INPUTS_DIR}/{path}" for path in study.inputs}:
        raise EvidenceError("input copies must cover original plan, specification and all model files")
    outputs = _outputs(study)
    if result.get("outputs") != outputs:
        raise EvidenceError("native output copies omit or repeat expected sample evidence")
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    rows = result.get("runs")
    if not isinstance(rows, list) or len(rows) != len(study.cases):
        raise EvidenceError("execution records do not match every expected sample and resolution")
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    measured, points, failures, runs = {}, {}, [], []
    total_bytes = 0
    for case, row in zip(study.cases, rows):
        _remaining(deadline)
        output = root / RESULTS_DIR / "native" / case.id
        execution = row.get("execution") if isinstance(row, dict) else None
        if (not isinstance(row, dict) or row.get("id") != case.id or not isinstance(execution, dict)
                or execution.get("command") != _command(case) or execution.get("cwd") != str(output / "inputs")
                or execution.get("log") != str(output / "ngspice.log")
                or type(execution.get("exit_code")) is not int or execution["exit_code"] != 0):
            raise EvidenceError("native execution identity, path or exit status disagrees")
        total_bytes += sum((output / path).stat().st_size for path in _files(study))
        if total_bytes > MAX_STUDY_OUTPUT_BYTES:
            raise EvidenceError("analog study exceeds its aggregate output budget")
        plot = _plot(root, study, case, output)
        if replay:
            with tempfile.TemporaryDirectory(prefix="analog-replay-") as directory:
                replay_output = Path(directory) / "native"
                _execute(root, study, case, replay_output, deadline=deadline)
                if plot != _plot(root, study, case, replay_output):
                    raise EvidenceError(f"{case.id}: native waveform differs from independent replay")
        values, valid = {}, True
        for check in case.analysis["checks"]:
            try:
                value, unit = measure(plot, check)
                if unit != check["unit"] or not math.isfinite(value):
                    raise EvidenceError("measurement is nonfinite or has the wrong physical unit")
                values[check["id"]] = value
            except EvidenceError as exc:
                valid = False
                failures.append({"kind": "invalid_measurement", "run": case.id, "check": check["id"], "reason": str(exc)})
        points[case.id] = len(plot.rows)
        if valid:
            measured[case.id] = values
        runs.append({"id": case.id, "scenario": case.scenario, "analysis": case.analysis["id"],
                     "resolution": case.resolution, "parameters": case.parameters,
                     "native_points": len(plot.rows), "valid": valid, "measurements": values})
    summaries, comparisons = [], []
    for analysis in study.specification["analyses"]:
        relevant = [case for case in study.cases if case.analysis["id"] == analysis["id"]]
        for check in analysis["checks"]:
            observations = []
            for case in relevant:
                if case.id not in measured:
                    continue
                value = measured[case.id][check["id"]]
                lower, upper = value-check["minimum"], check["maximum"]-value
                lower_surplus = lower-check.get("margin_lower", 0)
                upper_surplus = upper-check.get("margin_upper", 0)
                if not all(math.isfinite(v) for v in (lower, upper, lower_surplus, upper_surplus)):
                    raise EvidenceError("numerical headroom overflowed; use a meaningful signal scale")
                within = check["minimum"] <= value <= check["maximum"]
                margins = lower >= check.get("margin_lower", 0) and upper >= check.get("margin_upper", 0)
                observation = {"scenario": case.scenario, "run": case.id, "resolution": case.resolution,
                               "parameters": case.parameters,
                               "value": value, "lower_headroom": lower, "upper_headroom": upper,
                               "lower_margin_surplus": lower_surplus, "upper_margin_surplus": upper_surplus,
                               "within_limits": within, "required_margins_met": margins}
                observations.append(observation)
                if not within or not margins:
                    failures.append({"kind": "limit" if not within else "margin", "analysis": analysis["id"],
                                     "check": check["id"], "unit": check["unit"], **observation})
            summaries.append({
                "analysis": analysis["id"], "id": check["id"], "requirement": check["requirement"],
                "unit": check["unit"], "minimum": check["minimum"], "maximum": check["maximum"],
                "required_lower_margin": check.get("margin_lower", 0), "required_upper_margin": check.get("margin_upper", 0),
                "resolution_scope": ["coarse", "fine"],
                "expected_runs": len(relevant), "evaluated_runs": len(observations),
                "worst_observed_lower": min(observations, key=lambda row: row["lower_headroom"]) if observations else None,
                "worst_observed_upper": min(observations, key=lambda row: row["upper_headroom"]) if observations else None,
                "passed": len(observations) == len(relevant) and all(row["within_limits"] and row["required_margins_met"] for row in observations),
            })
        for scenario in study.scenarios:
            coarse, fine = (f"{scenario['id']}_{analysis['id']}_{resolution}" for resolution in ("coarse", "fine"))
            if coarse not in measured or fine not in measured:
                continue
            increased = analysis["kind"] == "op" or points[fine] > points[coarse]
            if not increased:
                failures.append({"kind": "sample_count", "scenario": scenario["id"], "analysis": analysis["id"]})
            for check in analysis["checks"]:
                delta = abs(measured[coarse][check["id"]] - measured[fine][check["id"]])
                if not math.isfinite(delta):
                    raise EvidenceError("refinement difference overflowed; use a meaningful signal scale")
                comparison = {"scenario": scenario["id"], "analysis": analysis["id"], "check": check["id"],
                              "unit": check["unit"], "max_delta": check["max_delta"], "delta": delta,
                              "method": "relative_tolerance" if analysis["kind"] == "op" else "grid_and_relative_tolerance",
                              "passed": increased and delta <= check["max_delta"]}
                comparisons.append(comparison)
                if delta > check["max_delta"]:
                    failures.append({"kind": "refinement", **comparison})
    expected = [case.id for case in study.cases]
    coverage = {
        "mode": "full_cartesian_plus_nominal", "axes": study.specification["axes"],
        "cartesian_points": study.grid_size, "expected_scenarios": len(study.scenarios),
        "scenarios": list(study.scenarios), "expected_runs": expected,
        "completed_runs": [row["id"] for row in rows], "measured_runs": list(measured),
        "complete": list(measured) == expected,
    }
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    _remaining(deadline)
    valid = coverage["complete"] and all(comparison["passed"] for comparison in comparisons)
    goal = study.specification["goal"]
    return {
        "status": "passed" if valid and not failures else "failed", "goal": goal,
        "conclusion_valid": valid, "task_accepted": valid and (goal == "diagnose" or not failures),
        "scope": SCOPE, "design": study.choices, "coverage": coverage,
        "checks": summaries, "comparisons": comparisons, "runs": runs, "failures": failures,
    }


def validate_robustness(root: Path) -> dict:
    root = root.resolve()
    report = _collect(root, resolve_study(root), replay=True)
    if record(root, ASSESSMENT) != report:
        raise EvidenceError("saved assessment differs from independently recomputed coverage, margins or refinements")
    if record(root, RESULTS).get("status") != ("complete" if report["task_accepted"] else "failed"):
        raise EvidenceError("study status disagrees with its fixed completion goal")
    if not report["task_accepted"]:
        raise EvidenceError(f"analog study is not accepted: inspect {ASSESSMENT}")
    return report


def run_robustness(root: Path) -> dict:
    root = root.resolve()
    study = resolve_study(root)
    version = ngspice_version()
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    result = {"operation": "ngspice-analog-corners", "status": "running", "execution_complete": False,
              "ngspice_version": version, "goal": study.specification["goal"], "cases": _describe(study),
              "inputs": {path: f"{INPUTS_DIR}/{path}" for path in study.inputs}, "outputs": {}, "runs": []}

    def save():
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n")

    save()
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    total_bytes = 0
    try:
        for source, target in result["inputs"].items():
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, source), root / target)
        for case in study.cases:
            if total_bytes >= MAX_STUDY_OUTPUT_BYTES:
                raise EvidenceError("analog study exhausted its aggregate output budget")
            row = {"id": case.id}
            result["runs"].append(row)

            def save_command(execution):
                row["execution"] = execution
                save()

            output = root / RESULTS_DIR / "native" / case.id
            _execute(root, study, case, output, deadline=deadline,
                     remaining_bytes=MAX_STUDY_OUTPUT_BYTES-total_bytes, save=save_command)
            total_bytes += sum((output / path).stat().st_size for path in _files(study))
            for path in _files(study):
                source = f"{RESULTS_DIR}/native/{case.id}/{path}"
                target = f"{RESULTS_DIR}/retained/{case.id}/{path}"
                (root / target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(project_file(root, source), root / target)
                result["outputs"][source] = target
            save()
        _remaining(deadline)
        result["execution_complete"] = True
        save()
        report = _collect(root, study, replay=False)
    except (EvidenceError, OSError, UnicodeError) as exc:
        result.update(status="failed", error=str(exc))
        (root / ASSESSMENT).write_text(json.dumps({
            "status": "incomplete", "goal": study.specification["goal"],
            "conclusion_valid": False, "task_accepted": False, "error": str(exc),
        }, indent=2) + "\n")
        save()
        raise
    (root / ASSESSMENT).write_text(json.dumps(report, indent=2) + "\n")
    result["status"] = "complete" if report["task_accepted"] else "failed"
    save()
    if not report["task_accepted"]:
        raise EvidenceError(f"analog study is not accepted: inspect {ASSESSMENT}")
    return report


# Execute only the declared ngspice analyses from frozen project-local inputs.


def run_analysis(root: Path) -> dict:
    root = root.resolve()
    if "robustness" in record(root, PLAN):
        return run_robustness(root)
    plan, required = validate_plan(root)
    if shutil.which("ngspice") is None:
        raise RuntimeError("ngspice is required; no simulation was performed")
    version = subprocess.run(
        ["ngspice", "--version"], capture_output=True, text=True, check=True, timeout=15,
    )
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    inputs = {}
    for relative in required:
        copy = f"{INPUTS_DIR}/{relative}"
        (root / copy).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / copy)
        inputs[relative] = copy
    results = {
        "tool_version": version.stdout + version.stderr,
        "environment": RUN_ENVIRONMENT, "inputs": inputs, "runs": [], "outputs": {},
    }
    result_path = root / RESULTS

    def save() -> None:
        result_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    save()
    for run in plan["runs"]:
        paths = run_paths(run["id"])
        (root / paths["raw"]).parent.mkdir(parents=True)
        command = run_command(run)
        row = {"id": run["id"], "command": command, "cwd": INPUTS_DIR, **paths}
        results["runs"].append(row)
        try:
            executed = subprocess.run(
                command, cwd=root / INPUTS_DIR, env={**os.environ, **RUN_ENVIRONMENT},
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            row.update(exit_code=None, error="ngspice exceeded 120 seconds")
            (root / paths["console"]).write_text(str(exc), encoding="utf-8")
            save()
            raise RuntimeError(f"{run['id']}: ngspice timed out; partial output is in {paths['log']}") from exc
        row["exit_code"] = executed.returncode
        (root / paths["console"]).write_text(
            "$ " + json.dumps(command) + "\n" + executed.stdout + executed.stderr,
            encoding="utf-8",
        )
        save()
        if executed.returncode != 0:
            raise RuntimeError(f"{run['id']}: ngspice exited {executed.returncode}; inspect {paths['log']}")
        for relative in paths.values():
            copy = relative.replace(RESULTS_DIR + "/runs/", RESULTS_DIR + "/retained/", 1)
            (root / copy).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), root / copy)
            results["outputs"][relative] = copy
        save()
    return validate_simulation(root)


# Per-stage completion check.

STAGES = ("specification", "model", "simulation", "review")


def stage_issues(stage: str, root: Path) -> list[str]:
    root = root.resolve()
    try:
        robustness = "robustness" in record(root, PLAN)
        if robustness and stage in {"specification", "model"}:
            resolve_study(root)
        elif stage == "specification":
            validate_specification(root)
        elif stage == "model":
            validate_model(root)
        else:
            validate_simulation(root)
            if stage == "review":
                project_file(root, REVIEW)
    except (EvidenceError, OSError, UnicodeError) as exc:
        return [str(exc)]
    return []


# Reference studies with independent equations.


def prepare_reference(root: Path) -> None:
    """RC operating point, DC transfer, AC and step response plus a finite-gain one-pole amplifier."""
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("models", "benches", "analog"):
        (root / directory).mkdir()
    for source in (Path(__file__).resolve().parent / "reference").iterdir():
        destination = "models" if source.suffix == ".inc" else "benches"
        if source.suffix in {".inc", ".cir"}:
            shutil.copyfile(source, root / destination / source.name)
    models = {}
    for directory in ("models", "benches"):
        for source in sorted((root / directory).iterdir()):
            models[source.relative_to(root).as_posix()] = {
                "kind": "testbench" if directory == "benches" else "ideal" if source.stem == "rc" else "behavioral",
                "source": "Hand-written reference; independently predicted by RC and one-pole feedback equations.",
                "validity": "Linear model, 27 C, and the explicit excitation/sweep ranges in the deck.",
                "limitations": ["No component parasitics, supply rails, saturation, slew limit, noise or process qualification."],
            }
    cutoff = 1 / (2 * math.pi * 1000 * 100e-9)
    gain = 100000 / (1 + 100000 / 11)
    bandwidth = 10 * (1 + 100000 / 11)

    def check(identity, requirement, statistic, unit, low, high, **fields):
        return {
            "id": identity, "requirement": requirement, "vector": "v(out)",
            "component": "real", "statistic": statistic, "unit": unit,
            "minimum": low, "maximum": high, **fields,
        }

    plan = {
        "objective": "Check ideal RC and finite-gain one-pole feedback responses, not hardware qualification.",
        "requirements": {
            "rc_dc": "The RC passes DC without load-induced attenuation.",
            "rc_bandwidth": "RC bandwidth agrees with 1/(2*pi*R*C).",
            "rc_step": "RC time constant agrees with R*C.",
            "amplifier_gain": "Feedback gain reflects finite open-loop gain, not an ideal infinite-gain assumption.",
            "amplifier_bandwidth": "Closed-loop bandwidth agrees with the explicitly one-pole model.",
        },
        "limitations": ["These independent equations apply only to the stated ideal/behavioral models."],
        "models": models,
        "runs": [
            {"id": "rc_op", "kind": "op", "netlist": "benches/rc_op.cir", "checks": [
                check("bias", "rc_dc", "point", "V", 0.999, 1.001),
            ]},
            {"id": "rc_dc", "kind": "dc", "netlist": "benches/rc_dc.cir", "checks": [
                check("midpoint", "rc_dc", "at", "V", 0.499, 0.501, at=0.5),
            ]},
            {"id": "rc_ac", "kind": "ac", "netlist": "benches/rc_ac.cir", "checks": [
                check("cutoff", "rc_bandwidth", "crossing", "Hz", cutoff * 0.997, cutoff * 1.003,
                      denominator="v(in)", component="magnitude", level=1 / math.sqrt(2),
                      direction="falling", window=[100, 10000]),
                check("phase", "rc_bandwidth", "at", "deg", -45.1, -44.9,
                      denominator="v(in)", component="phase_deg", at=cutoff),
            ]},
            {"id": "rc_tran", "kind": "tran", "netlist": "benches/rc_tran.cir", "checks": [
                check("time_constant", "rc_step", "crossing", "s", 99e-6, 101e-6,
                      level=1 - math.exp(-1), direction="rising", window=[1e-8, 0.0005]),
            ]},
            {"id": "amplifier_op", "kind": "op", "netlist": "benches/amplifier_op.cir", "checks": [
                check("bias", "amplifier_gain", "point", "V", gain * 0.1 * 0.999, gain * 0.1 * 1.001),
            ]},
            {"id": "amplifier_ac", "kind": "ac", "netlist": "benches/amplifier_ac.cir", "checks": [
                check("gain", "amplifier_gain", "at", "1", 10.98, 11.01,
                      denominator="v(in)", component="magnitude", at=1000),
                check("bandwidth", "amplifier_bandwidth", "crossing", "Hz", bandwidth * 0.997, bandwidth * 1.003,
                      denominator="v(in)", component="magnitude", level=gain / math.sqrt(2),
                      direction="falling", window=[10000, 1000000]),
            ]},
        ],
    }
    (root / "analog/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def prepare_envelope_reference(root: Path, *, goal: str = "design", tight: bool = False) -> None:
    """Loaded RC and Shockley diode over 17 declared conditions with all four analysis kinds."""
    if goal not in ("design", "diagnose"):
        raise ValueError("goal must be design or diagnose")
    root.mkdir(parents=True, exist_ok=False)
    for name in ("design", "benches", "analog"):
        (root / name).mkdir()
    parameters = {
        "resistance": (1000, 500, 2000, "ohm"), "capacitance": (100e-9, 50e-9, 200e-9, "F"),
        "load": (10000, 5000, 20000, "ohm"), "input_v": (1, 0.5, 2, "V"),
        "temp_c": (27, -20, 100, "degC"),
    }
    (root / "design/parameters.inc").write_text(
        "* Original nominal parameters; not measured parts\n"
        + "".join(f".param {name}={values[0]:.17g}\n" for name, values in parameters.items())
    )
    (root / "design/circuit.inc").write_text(
        "Vin in 0 DC {input_v} AC 1\nRseries in out {resistance}\n"
        "Cshunt out 0 {capacitance} IC=0\nRload out 0 {load}\n"
        "Idiode 0 diode DC 0.001\nDreference diode 0 DREF\n"
        ".model DREF D(Is=1e-12 N=1 Rs=0 Cjo=0 Tt=0 EG=1.11 XTI=3 TNOM=27)\n"
        ".temp {temp_c}\n.options tnom=27\n"
    )
    methods = {"bias": ".op", "transfer": ".dc Vin 0 2 0.1",
               "frequency": ".ac dec 80 10 100000", "step": ".tran 1u 1m 0 1u uic"}
    kinds = {"bias": "op", "transfer": "dc", "frequency": "ac", "step": "tran"}
    for identity, directive in methods.items():
        (root / f"benches/{identity}.cir").write_text(
            "Original loaded RC and independent diode example\n"
            '.include "design/parameters.inc"\n.include "design/circuit.inc"\n'
            ".save v(in) v(out) v(diode)\n" + directive + "\n.end\n"
        )

    def check(identity, requirement, statistic, unit, low, high, delta, **fields):
        return {"id": identity, "requirement": requirement, "vector": "v(out)", "component": "real",
                "statistic": statistic, "unit": unit, "minimum": low, "maximum": high,
                "max_delta": delta, **fields}

    checks = {
        "bias": [
            check("dc_level", "bias", "point", "V", 0.85, 0.96, 1e-4, margin_lower=0.005, margin_upper=0.005),
            check("diode", "temperature", "point", "V", 0.4, 0.7, 1e-4, vector="v(diode)",
                  margin_lower=0.005, margin_upper=0.005),
        ],
        "transfer": [check("midpoint", "transfer", "at", "V", 0.4, 0.49, 1e-5, at=0.5)],
        "frequency": [
            check("gain", "frequency", "at", "1", 0.77 if tight else 0.70, 0.80 if tight else 0.88, 2e-4,
                  at=1000, denominator="v(in)", component="magnitude", margin_lower=0.001, margin_upper=0.001),
            check("phase", "frequency", "at", "deg", -36, -22, 0.03, at=1000,
                  denominator="v(in)", component="phase_deg", margin_lower=0.1, margin_upper=0.1),
            check("edge", "frequency", "crossing", "Hz", 1800, 3800, 2,
                  window=[100, 10000], denominator="v(in)", component="magnitude", level=0.5, direction="falling"),
        ],
        "step": [
            check("response", "step", "at", "V", 0.50, 0.72, 1e-4, at=0.0001),
            check("rise", "step", "crossing", "s", 50e-6, 110e-6, 2e-7,
                  window=[1e-8, 0.0005], level=0.5, direction="rising"),
        ],
    }
    spec = {
        "goal": goal, "source": "Original finite study with limits declared before native execution.",
        "limitations": ["Linear RC and illustrative memoryless diode; no process, noise or physical-device guarantee.",
                        "DC sweeps Vin explicitly; an OP compares solver tolerance, not an axis grid."],
        "parameter_file": "design/parameters.inc",
        "parameters": {
            name: {"nominal": values[0], "minimum": values[1], "maximum": values[2], "unit": values[3],
                   "source": "Original illustrative model range, not a commercial device rating."}
            for name, values in parameters.items()
        },
        "design_variables": {} if goal == "diagnose" else {
            "resistance": {"parameter": "resistance", "minimum": 800, "maximum": 1200,
                           "source": "Allowed single common resistance choice."},
        },
        "axes": [
            {"id": "r", "parameter": "resistance", "unit": "1", "factors": [0.9, 1.1], "source": "Declared resistor samples."},
            {"id": "c", "parameter": "capacitance", "unit": "1", "factors": [0.9, 1.1], "source": "Declared capacitor samples."},
            {"id": "load", "parameter": "load", "unit": "ohm", "values": [8000, 12000], "source": "Declared load samples."},
            {"id": "temperature", "parameter": "temp_c", "unit": "degC", "values": [0, 60], "source": "Diode model temperature only."},
        ],
        "relative_tolerances": [1e-4, 1e-6],
        "analyses": [{"id": identity, "kind": kinds[identity], "netlist": f"benches/{identity}.cir",
                      "checks": checks[identity]} for identity in methods],
    }
    (root / "design/operating.json").write_text(json.dumps(spec, indent=2) + "\n")
    plan = {
        "objective": "Assess all original loaded-RC and diode samples without relaxing requirements.",
        "requirements": {"bias": "Loaded DC level.", "transfer": "DC transfer at 0.5 V.",
                         "frequency": "Declared gain, phase and 0.5 V/V band edge, not a varying -3 dB definition.",
                         "step": "Zero-initial-condition step response.", "temperature": "Diode forward voltage over temperature."},
        "limitations": ["Finite samples and model equations are not physical qualification."],
        "models": {
            path: {"kind": "testbench" if path.startswith("benches/") else "device",
                   "source": "Original hand-written passive network and explicit Shockley diode.",
                   "validity": "Declared parameter ranges and native analyses.",
                   "limitations": ["No real device characterization, parasitics or electrothermal feedback."]}
            for path in ["design/parameters.inc", "design/circuit.inc", *(f"benches/{identity}.cir" for identity in methods)]
        },
        "robustness": {"specification": "design/operating.json", "design": {} if goal == "diagnose" else {"resistance": 1000}},
    }
    (root / "analog/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="analog-evidence", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="read-only check of one stage's records and native waveforms")
    check.add_argument("--project-root", type=Path, default=Path("."))
    check.add_argument("--stage", choices=STAGES, required=True)
    run = commands.add_parser("run", help="execute analog/PLAN.json with ngspice into a new analog/results")
    run.add_argument("--project-root", type=Path, default=Path("."))
    reference = commands.add_parser("reference", help="six native RC/amplifier analyses against independent equations")
    reference.add_argument("output", type=Path, help="new directory; existing work is never overwritten")
    envelope = commands.add_parser("envelope-reference", help="loaded-RC and diode operating-envelope study")
    envelope.add_argument("output", type=Path, help="new directory; existing work is never overwritten")
    envelope.add_argument("--goal", choices=("design", "diagnose"), default="design")
    envelope.add_argument("--tight", action="store_true",
                          help="original narrower gain requirement; nominal passes, some corners fail")
    args = parser.parse_args(argv)
    if args.command == "check":
        issues = stage_issues(args.stage, args.project_root)
        for issue in issues:
            print(f"ERROR: {issue}", file=sys.stderr)
        if issues:
            return 1
        print(f"OK: analog {args.stage} record checks passed; this does not qualify a physical circuit")
        return 0
    try:
        if args.command == "reference":
            prepare_reference(args.output.resolve())
        elif args.command == "envelope-reference":
            prepare_envelope_reference(args.output.resolve(), goal=args.goal, tight=args.tight)
        result = run_analysis(args.project_root if args.command == "run" else args.output)
    except (EvidenceError, RuntimeError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    if args.command == "reference":
        print("PASS: six native analyses; only the stated ideal/behavioral circuit models were checked")
    else:
        print("PASS: requested numerical task accepted; a diagnosis may report noncompliance, never hardware approval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
