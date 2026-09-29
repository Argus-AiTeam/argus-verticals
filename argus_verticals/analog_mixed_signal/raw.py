"""Read one native ASCII ngspice plot and measure declared signals in SI units."""
from __future__ import annotations

import bisect
import cmath
import math
from dataclasses import dataclass
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError

PLOT_NAMES = {
    "op": "Operating Point",
    "dc": "DC transfer characteristic",
    "ac": "AC Analysis",
    "tran": "Transient Analysis",
}
UNITS = {"voltage": "V", "current": "A", "time": "s", "frequency": "Hz"}
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
                if quantity not in UNITS:
                    raise EvidenceError(f"unsupported signal quantity: {quantity}")
                return [row[index] for row in self.rows], UNITS[quantity]
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
    return crossings[0], UNITS[plot.variables[0][1]]
