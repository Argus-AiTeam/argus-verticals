"""Build real-reference, single-ended networks with scikit-rf, without implicit resampling."""
from __future__ import annotations

import io
import platform
import re
import warnings
from pathlib import Path

import numpy as np
import skrf as rf
from skrf.io.touchstone import Touchstone

from argus_verticals.hardware.shared.evidence import EvidenceError, names, number, project_file

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
