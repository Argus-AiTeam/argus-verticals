"""Run declared RF network studies with scikit-rf and check their retained evidence.

Standalone, adapted from Argus rf_design (networks, evidence, study, robustness, run_analysis)
and its shared hardware record checks. Needs numpy and scikit-rf; see evidence-contract.md.
"""
from __future__ import annotations

import argparse
import copy
import io
import itertools
import json
import math
import platform
import re
import shutil
import sys
import time
import warnings
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

try:  # --help works without them; every command reports what is missing
    import numpy as np
    import skrf as rf
    from skrf.io.touchstone import Touchstone
except ImportError as exc:
    MISSING = exc
else:
    MISSING = None

STAGES = ("specification", "model", "analysis", "review")
PLAN = "rf/PLAN.json"
RESULTS_DIR = "rf/results"
INPUTS_DIR = RESULTS_DIR + "/inputs"
RESULTS = RESULTS_DIR + "/RESULTS.json"
REVIEW = "rf/REVIEW.md"
OPERATION = "scikit-rf-network-studies"
METRICS = ("s_real", "s_imag", "s_magnitude", "s_db", "s_phase_deg", "sigma_max", "reciprocity_error")


# Project records ---------------------------------------------------------------------------------

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


# Networks: real-reference, single-ended, built with scikit-rf without implicit resampling --------

MAX_POINTS = 10001
MAX_PORTS = 8
MAX_FILE_BYTES = 32 * 1024 * 1024


def text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field}: expected nonempty text")
    return value


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}", value):
        raise EvidenceError("use lowercase underscore identifiers, at most 48 characters")
    return value


def positive(value: object, field: str) -> float:
    result = number(value, field)
    if result <= 0:
        raise EvidenceError(f"{field}: expected a positive SI value")
    return result


def references(value: object, ports: int) -> np.ndarray:
    if not isinstance(value, list) or len(value) != ports:
        raise EvidenceError(f"z0_ohm: declare exactly {ports} positive real port references")
    return np.array([positive(item, "z0_ohm") for item in value])


def validate_network(network: rf.Network) -> rf.Network:
    if not 1 <= len(network.f) <= MAX_POINTS or not 1 <= network.nports <= MAX_PORTS:
        raise EvidenceError("network reader supports 1-10001 frequencies and 1-8 ports")
    if (
        not np.all(np.isfinite(network.f)) or np.any(network.f <= 0)
        or np.any(np.diff(network.f) <= 0)
    ):
        raise EvidenceError("frequency grid must be finite, positive and strictly increasing")
    if not np.all(np.isfinite(network.s)) or not np.all(np.isfinite(network.z0)):
        raise EvidenceError("network contains nonfinite S parameters or reference impedances")
    if np.any(network.z0.imag != 0) or np.any(network.z0.real <= 0):
        raise EvidenceError("this adapter requires positive real reference impedances")
    if not np.all(network.z0 == network.z0[0]):
        raise EvidenceError("frequency-dependent references are outside this adapter")
    network.s_def = "power"
    return network


def read_touchstone(root: Path, relative: str) -> rf.Network:
    path = project_file(root, relative)
    if not re.fullmatch(r"\.(?:s[1-8]p|ts)", path.suffix.lower()):
        raise EvidenceError("use a Touchstone .s1p-.s8p or .ts input, not a serialized Network")
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise EvidenceError("Touchstone input exceeds the 32 MiB reader limit")
        content = path.read_text(encoding="utf-8-sig")
        options = [
            line.split("!", 1)[0].strip().lower().split()
            for line in content.splitlines() if line.lstrip().startswith("#")
        ]
        if len(options) != 1 or len(options[0]) != 6:
            raise EvidenceError("declare one explicit '# Hz S RI R 50' style option line")
        _, unit, parameter, form, marker, impedance = options[0]
        if unit not in ("hz", "khz", "mhz", "ghz") or parameter != "s" or form not in ("ri", "ma", "db") or marker != "r":
            raise EvidenceError("Touchstone input must explicitly declare frequency units, S data, RI/MA/DB and R")
        positive(float(impedance), "Touchstone R")
        declared = {}
        for keyword, maximum in (("Number of Ports", MAX_PORTS), ("Number of Frequencies", MAX_POINTS)):
            values = re.findall(rf"(?im)^\s*\[{keyword}\]\s+(\d+)", content)
            if len(values) > 1:
                raise EvidenceError(f"duplicate Touchstone {keyword}")
            for value in values:
                if not 1 <= int(value) <= maximum:
                    raise EvidenceError(f"{keyword} exceeds this reader's supported range")
                declared[keyword] = int(value)
        stream = io.StringIO(content)
        stream.name = path.name
        with warnings.catch_warnings(), np.errstate(divide="raise", invalid="raise", over="raise"):
            warnings.simplefilter("error", RuntimeWarning)
            parsed = Touchstone(stream)
        if parsed.version not in ("1.0", "2.0", "2.1") or parsed.parameter != "s":
            raise EvidenceError("only Touchstone 1.0/2.0/2.1 S parameters are supported")
        if parsed.noise is not None or np.any(parsed.port_modes != "S"):
            raise EvidenceError("noise data and mixed-mode port definitions require another analysis")
        frequency, scattering = parsed.get_sparameter_arrays()
        for keyword, actual in (("Number of Ports", parsed.rank), ("Number of Frequencies", len(frequency))):
            if keyword in declared and declared[keyword] != actual:
                raise EvidenceError(f"Touchstone {keyword} disagrees with the parsed data")
        if (
            not 1 <= len(frequency) <= MAX_POINTS or not np.all(np.isfinite(frequency))
            or np.any(frequency <= 0) or np.any(np.diff(frequency) <= 0)
        ):
            raise EvidenceError("Touchstone frequency grid must be finite, positive and strictly increasing")
        network = rf.Network(f=frequency, s=scattering, z0=parsed.z0, s_def="power", name=path.stem)
        return validate_network(network)
    except (OSError, UnicodeError, ValueError, IndexError, TypeError, AssertionError, RuntimeError, FloatingPointError, RuntimeWarning) as exc:
        if isinstance(exc, EvidenceError):
            raise
        raise EvidenceError(f"{relative}: invalid Touchstone data: {exc}") from exc


def _primitive(node: dict, identity: str) -> rf.Network:
    frequencies = node.get("frequency_hz")
    if not isinstance(frequencies, list) or not 1 <= len(frequencies) <= MAX_POINTS:
        raise EvidenceError("frequency_hz: provide 1-10001 explicit positive frequency samples")
    frequency = np.array([positive(value, "frequency_hz") for value in frequencies])
    if np.any(np.diff(frequency) <= 0):
        raise EvidenceError("frequency_hz must be strictly increasing")
    z0 = references(node.get("z0_ohm"), 2)
    a = np.tile(np.eye(2, dtype=complex), (len(frequency), 1, 1))
    omega = 2 * np.pi * frequency
    if node["kind"] == "line":
        impedance = positive(node.get("impedance_ohm"), "line impedance_ohm")
        delay = number(node.get("delay_s"), "line delay_s")
        loss = number(node.get("loss_db"), "line loss_db")
        gamma_length = loss * np.log(10) / 20 + 1j * omega * delay
        a[:, 0, 0] = a[:, 1, 1] = np.cosh(gamma_length)
        a[:, 0, 1] = impedance * np.sinh(gamma_length)
        a[:, 1, 0] = np.sinh(gamma_length) / impedance
    else:
        elements = node.get("elements")
        if not isinstance(elements, list) or not 1 <= len(elements) <= 64:
            raise EvidenceError("lumped elements: declare 1-64 series/shunt R, L or C elements in order")
        for element in elements:
            if not isinstance(element, dict) or element.get("kind") not in ("R", "L", "C"):
                raise EvidenceError("element.kind: choose R, L or C")
            value = positive(element.get("value_si"), "element.value_si")
            impedance = (
                np.full(len(frequency), value, dtype=complex) if element["kind"] == "R"
                else 1j * omega * value if element["kind"] == "L"
                else 1 / (1j * omega * value)
            )
            section = np.tile(np.eye(2, dtype=complex), (len(frequency), 1, 1))
            if element.get("connection") == "series":
                section[:, 0, 1] = impedance
            elif element.get("connection") == "shunt":
                section[:, 1, 0] = 1 / impedance
            else:
                raise EvidenceError("element.connection: choose series or shunt")
            a = a @ section
    # A vector is ambiguous when frequency count equals port count; keep port references explicit.
    return rf.Network(f=frequency, a=a, z0=np.broadcast_to(z0, (len(frequency), 2)), s_def="power", name=identity)


def _renormalize_real(network: rf.Network, reference: np.ndarray) -> None:
    # Direct wave-basis conversion avoids the singular Z matrix of a thru or series element.
    ratio = np.sqrt(network.z0.real / reference)
    a, b = (ratio + 1 / ratio) / 2, (ratio - 1 / ratio) / 2
    diagonal = np.eye(network.nports)[None, :, :]
    incident = a[:, :, None] * diagonal + b[:, :, None] * network.s
    reflected = b[:, :, None] * diagonal + a[:, :, None] * network.s
    network.s = np.linalg.solve(
        incident.transpose(0, 2, 1), reflected.transpose(0, 2, 1),
    ).transpose(0, 2, 1)
    network.z0 = np.broadcast_to(reference, network.z0.shape)


def build_networks(root: Path, definitions: object, targets: list[str] | None = None) -> tuple[dict[str, rf.Network], list[str]]:
    if not isinstance(definitions, dict) or not 1 <= len(definitions) <= 64:
        raise EvidenceError("networks: declare 1-64 named network definitions")
    built: dict[str, rf.Network] = {}
    active: set[str] = set()
    files: set[str] = set()

    def visit(identity: str) -> rf.Network:
        identifier(identity)
        if identity in active:
            raise EvidenceError(f"cyclic network dependency: {identity}")
        if identity in built:
            return built[identity]
        if identity not in definitions:
            raise EvidenceError(f"unknown network: {identity}")
        active.add(identity)
        node = definitions[identity]
        if not isinstance(node, dict):
            raise EvidenceError(f"{identity}: expected a network definition")
        kind = node.get("kind")
        if kind not in ("touchstone", "lumped", "line", "cascade", "renormalize", "reorder"):
            raise EvidenceError(f"{identity}: unsupported network kind")
        if kind in ("touchstone", "lumped", "line"):
            text(node.get("source"), f"{identity}.source")
            text(node.get("validity"), f"{identity}.validity")
            names(node.get("limitations"), f"{identity}.limitations")
        if kind == "touchstone":
            relative = text(node.get("path"), "Touchstone path")
            network = read_touchstone(root, relative)
            labels = names(node.get("ports"), f"{identity}.ports")
            if len(labels) != network.nports:
                raise EvidenceError(f"{identity}: label every physical port in file order")
            network.port_names = labels
            files.add(relative)
        elif kind in ("lumped", "line"):
            network = _primitive(node, identity)
        elif kind == "cascade":
            inputs = node.get("inputs")
            if not isinstance(inputs, list) or not 2 <= len(inputs) <= 64:
                raise EvidenceError("cascade.inputs: declare at least two networks, left to right")
            networks = [visit(item) for item in inputs]
            if any(item.nports != 2 for item in networks):
                raise EvidenceError("cascade currently connects only two-port networks")
            network = networks[0].copy()
            for right in networks[1:]:
                if not np.array_equal(network.f, right.f):
                    raise EvidenceError("cascade frequency grids differ; no implicit resampling")
                if not np.array_equal(network.z0[:, 1], right.z0[:, 0]):
                    raise EvidenceError("cascade junction references differ; renormalize explicitly")
                network = network ** right
        else:
            network = visit(node.get("input")).copy()
            if kind == "renormalize":
                _renormalize_real(network, references(node.get("z0_ohm"), network.nports))
            else:
                order = node.get("ports")
                if (
                    not isinstance(order, list) or len(order) != network.nports
                    or any(type(port) is not int for port in order)
                    or set(order) != set(range(1, network.nports + 1))
                ):
                    raise EvidenceError("reorder.ports: provide a complete one-based port permutation")
                network.renumber([port - 1 for port in order], list(range(network.nports)))
        network.name = identity
        built[identity] = validate_network(network)
        active.remove(identity)
        return network

    try:
        with warnings.catch_warnings(), np.errstate(divide="raise", invalid="raise", over="raise"):
            warnings.simplefilter("error", RuntimeWarning)
            for identity in definitions if targets is None else targets:
                visit(identity)
    except (FloatingPointError, np.linalg.LinAlgError, RuntimeWarning) as exc:
        raise EvidenceError(f"RF network calculation is undefined or numerically invalid: {exc}") from exc
    return built, sorted(files)


def measurement(network: rf.Network, check: dict) -> tuple[float, str, float]:
    metric = check["metric"]
    unit = "1"
    frequency = network.f
    low, high = (check["at_hz"], check["at_hz"]) if check["statistic"] == "at" else check["window_hz"]
    if not frequency[0] <= low <= high <= frequency[-1]:
        raise EvidenceError("measurement lies outside the saved frequency grid")
    if metric == "sigma_max":
        values = np.linalg.svd(network.s, compute_uv=False)[:, 0]
    elif metric == "reciprocity_error":
        values = np.max(np.abs(network.s - network.s.transpose(0, 2, 1)), axis=(1, 2))
    else:
        ports = check.get("ports")
        if (
            not isinstance(ports, list) or len(ports) != 2
            or any(type(port) is not int or not 1 <= port <= network.nports for port in ports)
        ):
            raise EvidenceError("S measurement ports: [response port, incident port], one-based")
        signal = network.s[:, ports[0] - 1, ports[1] - 1]
        if metric == "s_real":
            values = signal.real
        elif metric == "s_imag":
            values = signal.imag
        elif metric == "s_magnitude":
            values = np.abs(signal)
        elif metric == "s_db":
            # Only selected samples and the brackets needed for scalar interpolation contribute.
            first = max(0, int(np.searchsorted(frequency, low, side="right"))-1)
            stop = int(np.searchsorted(frequency, high, side="left"))+1
            frequency, signal = frequency[first:stop], signal[first:stop]
            if np.any(signal == 0):
                raise EvidenceError("dB is not finite at a zero S parameter; use s_magnitude for exact nulls")
            values, unit = 20 * np.log10(np.abs(signal)), "dB"
        else:
            if np.any(signal == 0):
                raise EvidenceError("phase is undefined at a zero S parameter")
            values, unit = np.rad2deg(np.unwrap(np.angle(signal))), "deg"
    if not np.all(np.isfinite(values)):
        raise EvidenceError("nonfinite RF measurement")

    def at(position: float) -> float:
        return float(np.interp(position, frequency, values))

    if check["statistic"] == "at":
        return at(check["at_hz"]), unit, float(check["at_hz"])
    selected = (frequency > low) & (frequency < high)
    samples = np.concatenate(([at(low)], values[selected], [at(high)]))
    frequencies = np.concatenate(([low], frequency[selected], [high]))
    index = np.argmin(samples) if check["statistic"] == "min" else np.argmax(samples)
    return float(samples[index]), unit, float(frequencies[index])


def measure(network: rf.Network, check: dict) -> tuple[float, str]:
    value, unit, _ = measurement(network, check)
    return value, unit


def versions() -> dict[str, str]:
    return {"python": platform.python_version(), "numpy": np.__version__, "scikit-rf": rf.__version__}


def write_network(path: Path, network: rf.Network) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    network.frequency.unit = "hz"
    data = network.write_touchstone(
        filename=path, return_string=True, version="2.0", form="ri",
        write_noise=False, encoding="utf-8",
        format_spec_A="{:.17g}", format_spec_B="{:.17g}", format_spec_freq="{:.17g}",
    )
    if not isinstance(data, str) or not data.strip():
        raise EvidenceError("scikit-rf did not produce Touchstone output")
    if len(data.encode("utf-8")) > MAX_FILE_BYTES:
        raise EvidenceError("exported network exceeds the 32 MiB limit")
    path.write_text(data, encoding="utf-8")


def check_export(root: Path, relative: str, expected: rf.Network) -> rf.Network:
    exported = read_touchstone(root, relative)
    if (
        not np.array_equal(exported.f, expected.f)
        or not np.array_equal(exported.z0, expected.z0)
        or exported.s.shape != expected.s.shape
        or not np.allclose(exported.s, expected.s, rtol=1e-11, atol=1e-12)
    ):
        raise EvidenceError(f"{relative}: exported data disagrees with recomputation from current inputs")
    return exported


# Plan and network-study evidence ---------------------------------------------------------------

def validate_specification(root: Path) -> dict:
    plan = record(root, PLAN)
    text(plan.get("objective"), "objective")
    names(plan.get("limitations"), "limitations")
    requirements = plan.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise EvidenceError("requirements: map identifiers to observable RF requirements")
    for key, value in requirements.items():
        identifier(key)
        text(value, f"requirements.{key}")
    return plan


def validate_model(root: Path) -> dict:
    plan = validate_specification(root)
    if "robustness" in plan:
        study = resolve_study(root)
        build_networks(root, study.specification["networks"])
        return plan
    build_networks(root, plan.get("networks"))
    return plan


def validate_plan(root: Path) -> tuple[dict, dict, list[str]]:
    return validate_network_plan(root, validate_specification(root))


def validate_network_plan(root: Path, plan: dict) -> tuple[dict, dict, list[str]]:
    studies = plan.get("studies")
    if not isinstance(studies, list) or not 1 <= len(studies) <= 64:
        raise EvidenceError("studies: declare 1-64 selected network studies")
    if any(not isinstance(study, dict) for study in studies):
        raise EvidenceError("each study must be an object")
    networks, inputs = build_networks(
        root, plan.get("networks"), [identifier(study.get("network")) for study in studies],
    )
    ids, covered = [], set()
    for study in studies:
        if not isinstance(study, dict):
            raise EvidenceError("each study must be an object")
        ids.append(identifier(study.get("id")))
        target = identifier(study.get("network"))
        if target not in networks:
            raise EvidenceError(f"unknown study network: {target}")
        checks = study.get("checks")
        if not isinstance(checks, list) or not 1 <= len(checks) <= 128:
            raise EvidenceError("each study needs 1-128 numerical checks")
        check_ids = []
        for check in checks:
            if not isinstance(check, dict):
                raise EvidenceError("each check must be an object")
            check_ids.append(identifier(check.get("id")))
            requirement = identifier(check.get("requirement"))
            if requirement not in plan["requirements"]:
                raise EvidenceError(f"unknown requirement: {requirement}")
            covered.add(requirement)
            if check.get("metric") not in METRICS:
                raise EvidenceError(f"metric: choose one of {METRICS}")
            if check.get("unit") not in ("1", "dB", "deg"):
                raise EvidenceError("unit: use 1, dB or deg")
            low = number(check.get("minimum"), "minimum", minimum=-math.inf)
            high = number(check.get("maximum"), "maximum", minimum=-math.inf)
            if low > high:
                raise EvidenceError("minimum exceeds maximum")
            statistic = check.get("statistic")
            if statistic not in ("at", "min", "max"):
                raise EvidenceError("statistic: use at, min or max")
            if statistic == "at":
                number(check.get("at_hz"), "at_hz")
            else:
                window = check.get("window_hz")
                if not isinstance(window, list) or len(window) != 2:
                    raise EvidenceError("window_hz: declare [start, stop]")
                if number(window[0], "window start") >= number(window[1], "window stop"):
                    raise EvidenceError("window start must precede stop")
            if check["metric"].startswith("s_"):
                ports = check.get("ports")
                if (
                    not isinstance(ports, list) or len(ports) != 2
                    or any(type(port) is not int or not 1 <= port <= networks[target].nports for port in ports)
                ):
                    raise EvidenceError("ports: [response, incident], one-based, within the selected network")
        names(check_ids, "check ids")
    names(ids, "study ids")
    if covered != set(plan["requirements"]):
        raise EvidenceError("every numerical requirement needs a declared check")
    return plan, networks, sorted({PLAN, *inputs})


def result_path(identity: str) -> str:
    return f"{RESULTS_DIR}/networks/{identity}.ts"


def validate_analysis(root: Path) -> dict:
    if "robustness" in validate_specification(root):
        return validate_robustness(root)
    plan, networks, required = validate_plan(root)
    result = record(root, RESULTS)
    if result.get("operation") != OPERATION or result.get("status") != "complete":
        raise EvidenceError("RF calculation has no completed execution record")
    versions = result.get("versions")
    if not isinstance(versions, dict):
        raise EvidenceError("record the actual Python, numpy and scikit-rf versions")
    for key in ("python", "numpy", "scikit-rf"):
        text(versions.get(key), f"versions.{key}")
    expected_inputs = {relative: f"{INPUTS_DIR}/{relative}" for relative in required}
    if result.get("inputs") != expected_inputs:
        raise EvidenceError("input copies must match the plan and all actual Touchstone sources")
    current_files(root, result, required)
    studies = result.get("studies")
    if not isinstance(studies, list) or any(not isinstance(item, dict) for item in studies):
        raise EvidenceError("studies: expected execution records")
    executed_ids = names([item.get("id") for item in studies], "executed study ids")
    requested = {study["id"]: study for study in plan["studies"]}
    if set(executed_ids) != set(requested):
        raise EvidenceError("executed studies must match the requested studies exactly")
    expected_outputs = {
        result_path(identity): f"{RESULTS_DIR}/retained/{identity}.ts"
        for identity in requested
    }
    if result.get("outputs") != expected_outputs:
        raise EvidenceError("retain independent copies of every exported network")
    current_files(root, result, list(expected_outputs), field="outputs")
    measured = {}
    for row in studies:
        study = requested[row["id"]]
        if row.get("network") != study["network"] or row.get("path") != result_path(row["id"]):
            raise EvidenceError("study output does not identify the requested network")
        exported = check_export(root, row["path"], networks[study["network"]])
        values = {}
        for check in study["checks"]:
            value, unit = measure(exported, check)
            if unit != check["unit"]:
                raise EvidenceError(f"{row['id']}/{check['id']}: measured {unit}, not {check['unit']}")
            if not math.isfinite(value) or not check["minimum"] <= value <= check["maximum"]:
                raise EvidenceError(
                    f"{row['id']}/{check['id']}: {value:g} {unit} outside "
                    f"[{check['minimum']:g}, {check['maximum']:g}]"
                )
            values[check["id"]] = value
        measured[row["id"]] = values
    return measured


# Robustness: complete finite component samples and explicit frequency-grid refinements ----------

MAX_SCENARIOS = 17
MAX_SCATTERING_ENTRIES = 2_000_000
MAX_INPUT_BYTES = 4 * 1024 * 1024
CHECK_FIELDS = {
    "id", "requirement", "metric", "ports", "statistic", "at_hz", "window_hz",
    "unit", "minimum", "maximum", "margin_lower", "margin_upper", "max_delta",
}
ASSESSMENT = RESULTS_DIR + "/ASSESSMENT.json"
ROBUSTNESS_OPERATION = "scikit-rf-component-corners"
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_STUDY_SECONDS = 180
SCOPE = "Finite Cartesian component samples and sampled-frequency refinement; no continuous-band, continuous-tolerance, yield or physical qualification."


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


def _cases(study: Study):
    for scenario in study.scenarios:
        for resolution in ("coarse", "fine"):
            yield f"{scenario['id']}_{resolution}", scenario, resolution


def _rows(study: Study) -> list[dict]:
    return [
        {"id": identity, "scenario": scenario["id"], "resolution": resolution, "parameters": scenario["parameters"],
         "model": f"{RESULTS_DIR}/cases/{identity}/MODEL.json",
         "studies": [{"id": item["id"], "network": item["network"],
                      "path": f"{RESULTS_DIR}/cases/{identity}/{item['id']}.ts"} for item in study.specification["studies"]]}
        for identity, scenario, resolution in _cases(study)
    ]


def _outputs(study: Study) -> dict[str, str]:
    return {
        source: f"{RESULTS_DIR}/retained/{row['id']}/{Path(source).name}"
        for row in _rows(study) for source in (row["model"], *(item["path"] for item in row["studies"]))
    }


def _budget(deadline: float, size: int) -> None:
    if time.monotonic() > deadline or size > MAX_OUTPUT_BYTES:
        raise EvidenceError("RF robustness exceeds its 180-second or 128-MiB aggregate budget")


def headroom(value: float, check: dict) -> dict:
    exact = Fraction(str(value))
    lower = exact-Fraction(str(check["minimum"]))
    upper = Fraction(str(check["maximum"]))-exact
    lower_surplus = lower-Fraction(str(check.get("margin_lower", 0)))
    upper_surplus = upper-Fraction(str(check.get("margin_upper", 0)))
    try:
        distances = dict(zip(
            ("lower_headroom", "upper_headroom", "lower_margin_surplus", "upper_margin_surplus"),
            map(float, (lower, upper, lower_surplus, upper_surplus)),
        ))
    except OverflowError as exc:
        raise EvidenceError("RF headroom overflowed; use a meaningful measurement scale") from exc
    if not all(math.isfinite(v) for v in distances.values()):
        raise EvidenceError("RF headroom overflowed; use a meaningful measurement scale")
    return {
        **distances,
        "within_limits": check["minimum"] <= value <= check["maximum"],
        "required_margins_met": lower_surplus >= 0 and upper_surplus >= 0,
    }


def _collect(root: Path, study: Study) -> dict:
    result = record(root, RESULTS)
    if result.get("operation") != ROBUSTNESS_OPERATION or result.get("execution_complete") is not True:
        raise EvidenceError("RF tolerance execution is incomplete")
    if result.get("versions") != versions():
        raise EvidenceError("installed RF calculation versions differ from recorded execution")
    if result.get("goal") != study.specification["goal"] or result.get("cases") != _rows(study):
        raise EvidenceError("recorded cases differ from complete original RF tolerance coverage")
    if result.get("inputs") != {path: f"{INPUTS_DIR}/{path}" for path in study.inputs}:
        raise EvidenceError("input copies must cover original plan and RF specification")
    outputs = _outputs(study)
    if result.get("outputs") != outputs:
        raise EvidenceError("retain every generated model and exported case network")
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    size = 0
    failures, runs, observations, measured = [], [], {}, {}
    for (identity, scenario, resolution), row in zip(_cases(study), result["cases"]):
        _budget(deadline, size)
        definitions = rendered_networks(study, scenario, resolution)
        if project_file(root, row["model"]).read_bytes() != model_bytes(definitions):
            raise EvidenceError(f"{identity}: generated model differs from the original common design and sample")
        networks, _ = build_networks(root, definitions, [item["network"] for item in study.specification["studies"]])
        for item, saved in zip(study.specification["studies"], row["studies"]):
            size += project_file(root, saved["path"]).stat().st_size
            _budget(deadline, size)
            network = check_export(root, saved["path"], networks[item["network"]])
            sigma = float(np.max(np.linalg.svd(network.s, compute_uv=False)[:, 0]))
            reciprocity = float(np.max(np.abs(network.s-network.s.transpose(0, 2, 1))))
            valid = sigma <= 1+1e-9 and reciprocity <= 1e-9
            if not valid:
                failures.append({"kind": "network_physics", "case": identity, "study": item["id"],
                                 "sigma_max": sigma, "reciprocity_error": reciprocity})
            values = {}
            for check in item["checks"]:
                key = (item["id"], check["id"])
                observations.setdefault(key, [])
                try:
                    value, unit, frequency = measurement(network, check)
                    if unit != check["unit"] or not math.isfinite(value):
                        raise EvidenceError("measurement unit or finiteness differs from the original check")
                except EvidenceError as exc:
                    valid = False
                    failures.append({"kind": "invalid_measurement", "case": identity, "study": item["id"],
                                     "check": check["id"], "reason": str(exc)})
                    continue
                observation = {
                    "case": identity, "scenario": scenario["id"], "resolution": resolution,
                    "parameters": scenario["parameters"], "frequency_hz": frequency, "value": value,
                    **headroom(value, check),
                }
                observations[key].append(observation)
                values[check["id"]] = {"value": value, "frequency_hz": frequency}
                if not observation["within_limits"] or not observation["required_margins_met"]:
                    failures.append({"kind": "limit" if not observation["within_limits"] else "margin",
                                     "study": item["id"], "check": check["id"], "unit": unit, **observation})
            measured[(identity, item["id"])] = values
            runs.append({"case": identity, "study": item["id"], "network": item["network"],
                         "frequency_points": len(network.f), "sigma_max": sigma,
                         "reciprocity_error": reciprocity, "valid": valid, "measurements": values})
        size += project_file(root, row["model"]).stat().st_size
    checks, comparisons = [], []
    for item in study.specification["studies"]:
        for check in item["checks"]:
            values = observations[(item["id"], check["id"])]
            expected = 2 * len(study.scenarios)
            checks.append({
                "study": item["id"], "id": check["id"], "requirement": check["requirement"], "unit": check["unit"],
                "minimum": check["minimum"], "maximum": check["maximum"],
                "required_lower_margin": check.get("margin_lower", 0), "required_upper_margin": check.get("margin_upper", 0),
                "expected_cases": expected, "evaluated_cases": len(values),
                "worst_observed_lower": min(values, key=lambda row: row["lower_headroom"]) if values else None,
                "worst_observed_upper": min(values, key=lambda row: row["upper_headroom"]) if values else None,
                "passed": len(values) == expected and all(v["within_limits"] and v["required_margins_met"] for v in values),
            })
            for scenario in study.scenarios:
                pair = [measured[(f"{scenario['id']}_{resolution}", item["id"])] for resolution in ("coarse", "fine")]
                if any(check["id"] not in row for row in pair):
                    continue
                delta = abs(pair[1][check["id"]]["value"] - pair[0][check["id"]]["value"])
                if not math.isfinite(delta):
                    raise EvidenceError("RF refinement difference overflowed")
                comparison = {"scenario": scenario["id"], "study": item["id"], "check": check["id"],
                              "unit": check["unit"], "delta": delta, "max_delta": check["max_delta"],
                              "passed": delta <= check["max_delta"]}
                comparisons.append(comparison)
                if not comparison["passed"]:
                    failures.append({"kind": "refinement", **comparison})
    coverage = {
        "mode": "full_cartesian_plus_nominal", "axes": study.specification["axes"],
        "cartesian_points": study.grid_size, "expected_scenarios": len(study.scenarios),
        "scenarios": list(study.scenarios), "expected_cases": [row["id"] for row in _rows(study)],
        "completed_cases": [row["id"] for row in result["cases"]],
        "complete": all(run["valid"] for run in runs),
    }
    valid = coverage["complete"] and all(row["passed"] for row in comparisons)
    accepted = valid and (study.specification["goal"] == "diagnose" or not failures)
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    _budget(deadline, size)
    return {
        "goal": study.specification["goal"], "status": "passed" if valid and not failures else "failed",
        "conclusion_valid": valid, "task_accepted": accepted, "scope": SCOPE,
        "design": study.choices, "coverage": coverage, "checks": checks,
        "comparisons": comparisons, "runs": runs, "failures": failures,
    }


def inspect_study(root: Path) -> dict:
    root = root.resolve()
    report = _collect(root, resolve_study(root))
    if record(root, ASSESSMENT) != report:
        raise EvidenceError("saved RF assessment differs from independent coverage, measurement or margin calculations")
    if record(root, RESULTS).get("status") != ("complete" if report["task_accepted"] else "failed"):
        raise EvidenceError("execution status differs from the original task goal")
    return report


def validate_robustness(root: Path) -> dict:
    report = inspect_study(root)
    if not report["task_accepted"]:
        raise EvidenceError(f"RF robustness task is not accepted; inspect {ASSESSMENT}")
    return report


def run_robustness(root: Path) -> dict:
    root = root.resolve()
    study = resolve_study(root)
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    result = {
        "operation": ROBUSTNESS_OPERATION, "versions": versions(), "goal": study.specification["goal"],
        "status": "running", "execution_complete": False, "inputs": {}, "cases": [], "outputs": {},
    }

    def save() -> None:
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for relative in study.inputs:
            target = f"{INPUTS_DIR}/{relative}"
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), root / target)
            result["inputs"][relative] = target
        save()
        current_files(root, result, list(study.inputs))
        frozen = resolve_study(root / INPUTS_DIR)
        if frozen != study:
            raise EvidenceError("RF inputs changed while copying the original specification")
        deadline, size = time.monotonic()+MAX_STUDY_SECONDS, 0
        outputs = _outputs(frozen)
        for (identity, scenario, resolution), row in zip(_cases(frozen), _rows(frozen)):
            _budget(deadline, size)
            definitions = rendered_networks(frozen, scenario, resolution)
            model = root / row["model"]
            model.parent.mkdir(parents=True, exist_ok=False)
            model.write_bytes(model_bytes(definitions))
            networks, _ = build_networks(root / INPUTS_DIR, definitions, [item["network"] for item in frozen.specification["studies"]])
            for item in row["studies"]:
                write_network(root / item["path"], networks[item["network"]])
            for source in (row["model"], *(item["path"] for item in row["studies"])):
                size += (root / source).stat().st_size
                _budget(deadline, size)
                retained = outputs[source]
                (root / retained).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / source, root / retained)
                result["outputs"][source] = retained
            result["cases"].append(row)
            save()
        result["execution_complete"] = True
        save()
        report = _collect(root, study)
        (root / ASSESSMENT).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        result["status"] = "complete" if report["task_accepted"] else "failed"
        save()
        if not report["task_accepted"]:
            raise EvidenceError(f"RF robustness task failed original limits or numerical validity; inspect {ASSESSMENT}")
        return report
    except (EvidenceError, OSError, ValueError) as exc:
        result.update(status="failed", error=str(exc))
        save()
        raise


# Runner and stage checks -----------------------------------------------------------------------

def run_analysis(root: Path) -> dict:
    root = root.resolve()
    if "robustness" in validate_specification(root):
        return run_robustness(root)
    _, _, required = validate_plan(root)
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    inputs = {}
    for relative in required:
        target = f"{INPUTS_DIR}/{relative}"
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / target)
        inputs[relative] = target
    result = {
        "operation": OPERATION, "status": "running",
        "versions": versions(),
        "inputs": inputs, "studies": [], "outputs": {},
    }

    def save() -> None:
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        plan, networks, _ = validate_plan(root / INPUTS_DIR)
        for study in plan["studies"]:
            relative = result_path(study["id"])
            path = root / relative
            write_network(path, networks[study["network"]])
            retained = f"{RESULTS_DIR}/retained/{study['id']}.ts"
            (root / retained).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, root / retained)
            result["studies"].append({"id": study["id"], "network": study["network"], "path": relative})
            result["outputs"][relative] = retained
            save()
        result["status"] = "complete"
        save()
        measurements = validate_analysis(root)
    except (EvidenceError, OSError, ValueError) as exc:
        result.update(status="failed", error=str(exc))
        save()
        raise
    return measurements


def stage_completion_issues(stage: str, project_root: Path) -> tuple[str, ...]:
    try:
        if stage == "specification":
            validate_specification(project_root)
        elif stage == "model":
            validate_model(project_root)
        elif stage == "analysis":
            validate_analysis(project_root)
        elif stage == "review":
            validate_analysis(project_root)
            project_file(project_root, REVIEW)
        else:
            raise ValueError(f"unknown RF stage: {stage}")
    except EvidenceError as exc:
        return (str(exc),)
    return ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence.py", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="calculate the studies in rf/PLAN.json into a new rf/results")
    check = commands.add_parser("check", help="read-only: print the stage's issues; [] and exit 0 when none")
    check.add_argument("--stage", choices=STAGES, required=True)
    inspect = commands.add_parser("inspect", help="read-only: recompute a robustness assessment, accepted or not")
    for command in (run, check, inspect):
        command.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    if MISSING:
        sys.exit(f"FAIL: evidence.py needs numpy and scikit-rf (see Needs in SKILL.md): {MISSING}")
    root = args.project_root.resolve()
    if args.command == "check":
        issues = stage_completion_issues(args.stage, root)
        print(list(issues))
        return int(bool(issues))
    try:
        report = run_analysis(root) if args.command == "run" else inspect_study(root)
    except (EvidenceError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    if args.command == "inspect":
        print(f"CONSISTENT: {ASSESSMENT} matches an independent recomputation; task_accepted={report['task_accepted']}")
    elif "task_accepted" in report:
        print("ACCEPTED: declared RF task goal; inspect ASSESSMENT.json for passed or failed original limits")
    else:
        print("PASS: declared RF network checks; no full-wave, calibration or hardware qualification claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
