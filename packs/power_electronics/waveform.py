"""Time-weighted native measurements and source/load/loss/storage accounting.

Adapted from the Argus power_electronics/waveform.py with the standard library in place of numpy:
the same formulas, windows and limits.
"""
from __future__ import annotations

import bisect
import math

from shared import EvidenceError, Plot

VOLTAGES = ("in", "out", "cap", "sw", "pwm", "conductance")
CURRENTS = ("vin", "lpower", "vswitch", "vrect", "vload")
BALANCE_LIMIT = 1e-3
STEADY_DRIFT_LIMIT = 5e-3


def product_integral(time, left, right) -> float:
    # Exact integral of the product of two piecewise-linear native signals.
    return math.fsum(
        (t1 - t0) / 6 * (2*a0*b0 + a0*b1 + a1*b0 + 2*a1*b1)
        for t0, t1, a0, a1, b0, b1 in zip(time, time[1:], left, left[1:], right, right[1:])
    )


def measurements(plot: Plot, model: dict, run: dict) -> dict[str, dict[str, float]]:
    axis = [row[0].real for row in plot.rows]
    signals = {}
    for names, kind, unit in ((VOLTAGES, "v", "V"), (CURRENTS, "i", "A")):
        for name in names:
            values, actual = plot.signal(f"{kind}({name})")
            if actual != unit or any(value.imag != 0 for value in values):
                raise EvidenceError("native signal has wrong units or complex transient values")
            signals[name] = [value.real for value in values]
    source = run["input_voltage_v"]
    if any(abs(value - source) > 1e-12 + 1e-9 * abs(source) for value in signals["in"]):
        raise EvidenceError("saved input voltage differs from the declared source")
    if axis[0] > 1 / run["frequency_hz"] / 10:
        raise EvidenceError("native waveform does not include the beginning of startup")
    period = 1 / run["frequency_hz"]
    if max(b - a for a, b in zip(axis, axis[1:])) > run["max_step_s"] * (1 + 1e-8):
        raise EvidenceError("native waveform exceeds the declared maximum time step")

    def at(values, position, index):
        # Linear interpolation on [axis[index], axis[index + 1]], exact on a native sample.
        for exact in (index, index + 1):
            if axis[exact] == position:
                return values[exact]
        slope = (values[index + 1] - values[index]) / (axis[index + 1] - axis[index])
        return slope * (position - axis[index]) + values[index]

    def samples(low, high):
        if not axis[0] <= low < high <= axis[-1]:
            raise EvidenceError("observation interval is outside the native saved time range")
        first, stop = bisect.bisect_right(axis, low), bisect.bisect_left(axis, high)
        time = [low, *axis[first:stop], high]
        if len(time) < 20:
            raise EvidenceError("observation interval has insufficient native samples")
        return time, {
            key: [at(values, low, first - 1), *values[first:stop], at(values, high, stop - 1)]
            for key, values in signals.items()
        }

    def mean(time, value):
        return product_integral(time, value, [1.0] * len(value)) / (time[-1] - time[0])

    def minus(left, right):
        return [a - b for a, b in zip(left, right)]

    measured = {}
    for name, window in run["windows"].items():
        low, high = window["interval_s"]
        time, value = samples(low, high)
        vi, vo, vc, vs = (value[k] for k in ("in", "out", "cap", "sw"))
        ii, il, isw, ir, io = (value[k] for k in ("vin", "lpower", "vswitch", "vrect", "vload"))
        duration = high - low
        switch_voltage = minus(vi, vs) if model["topology"] == "buck" else vs
        diode_voltage = [-v for v in vs] if model["topology"] == "buck" else minus(vs, vo)
        esr_voltage = minus(vo, vc)
        input_energy = -product_integral(time, vi, ii)
        output_energy = product_integral(time, vo, io)
        loss = (
            model["inductor_resistance_ohm"] * product_integral(time, il, il)
            + product_integral(time, esr_voltage, esr_voltage) / model["capacitor_esr_ohm"]
            + product_integral(time, switch_voltage, isw)
            + product_integral(time, diode_voltage, ir)
        )
        storage = (
            0.5 * model["inductance_h"] * (il[-1]**2 - il[0]**2)
            + 0.5 * model["capacitance_f"] * (vc[-1]**2 - vc[0]**2)
        )
        if input_energy <= 0 or output_energy < 0 or loss < -abs(input_energy) * 1e-8:
            raise EvidenceError("source/load/loss energy has an unexpected sign")
        balance = abs(input_energy - output_energy - loss - storage) / input_energy
        if balance > BALANCE_LIMIT:
            raise EvidenceError(f"{name}: source/load/loss/storage balance exceeds 1e-3 relative error")
        first_t, first = samples(low, low + period)
        last_t, last = samples(high - period, high)
        drift = max(
            abs(mean(first_t, first[key]) - mean(last_t, last[key]))
            / max(abs(mean(first_t, first[key])), abs(mean(last_t, last[key])), 1e-12)
            for key in ("out", "lpower")
        )
        if window["kind"] == "steady" and drift > STEADY_DRIFT_LIMIT:
            raise EvidenceError(f"{name}: first/last cycle means are not steady within 0.5 percent")
        capacitor_current = [v / model["capacitor_esr_ohm"] for v in esr_voltage]
        values = {
            "output_mean_v": mean(time, vo), "output_min_v": min(vo),
            "output_max_v": max(vo), "output_pp_v": max(vo) - min(vo),
            "inductor_mean_a": mean(time, il), "inductor_min_a": min(il),
            "inductor_max_a": max(il), "inductor_pp_a": max(il) - min(il),
            "inductor_rms_a": math.sqrt(product_integral(time, il, il) / duration),
            "capacitor_rms_a": math.sqrt(product_integral(time, capacitor_current, capacitor_current) / duration),
            "switch_peak_v": max(abs(v) for v in switch_voltage), "switch_peak_a": max(abs(i) for i in isw),
            "rectifier_reverse_peak_v": max(max(-v, 0.0) for v in diode_voltage),
            "input_power_w": input_energy / duration, "output_power_w": output_energy / duration,
            "loss_power_w": loss / duration, "storage_rate_w": storage / duration,
            "energy_relative_error": balance, "cycle_mean_relative_change": drift,
        }
        if not all(math.isfinite(value) for value in values.values()):
            raise EvidenceError("nonfinite computed converter measurement")
        measured[name] = {key: float(value) for key, value in values.items()}
    return measured
