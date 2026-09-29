"""Time-weighted native measurements and source/load/loss/storage accounting."""
from __future__ import annotations

import math

import numpy as np

from argus_verticals.hardware.shared.evidence import EvidenceError
from argus_verticals.hardware.spice.raw import Plot

VOLTAGES = ("in", "out", "cap", "sw", "pwm", "conductance")
CURRENTS = ("vin", "lpower", "vswitch", "vrect", "vload")
BALANCE_LIMIT = 1e-3
STEADY_DRIFT_LIMIT = 5e-3


def product_integral(time, left, right) -> float:
    # Exact integral of the product of two piecewise-linear native signals.
    return float(np.sum(np.diff(time) / 6 * (
        2*left[:-1]*right[:-1] + left[:-1]*right[1:] + left[1:]*right[:-1] + 2*left[1:]*right[1:]
    )))


def measurements(plot: Plot, model: dict, run: dict) -> dict[str, dict[str, float]]:
    axis = np.array([row[0].real for row in plot.rows])
    signals = {}
    for names, kind, unit in ((VOLTAGES, "v", "V"), (CURRENTS, "i", "A")):
        for name in names:
            values, actual = plot.signal(f"{kind}({name})")
            if actual != unit or any(value.imag != 0 for value in values):
                raise EvidenceError("native signal has wrong units or complex transient values")
            signals[name] = np.array([value.real for value in values])
    if not np.allclose(signals["in"], run["input_voltage_v"], rtol=1e-9, atol=1e-12):
        raise EvidenceError("saved input voltage differs from the declared source")
    if axis[0] > 1 / run["frequency_hz"] / 10:
        raise EvidenceError("native waveform does not include the beginning of startup")
    period = 1 / run["frequency_hz"]
    if np.max(np.diff(axis)) > run["max_step_s"] * (1 + 1e-8):
        raise EvidenceError("native waveform exceeds the declared maximum time step")

    def samples(low, high):
        if not axis[0] <= low < high <= axis[-1]:
            raise EvidenceError("observation interval is outside the native saved time range")
        time = np.r_[low, axis[(axis > low) & (axis < high)], high]
        if len(time) < 20:
            raise EvidenceError("observation interval has insufficient native samples")
        return time, {key: np.interp(time, axis, values) for key, values in signals.items()}

    def mean(time, value):
        return product_integral(time, value, np.ones_like(value)) / (time[-1] - time[0])

    measured = {}
    for name, window in run["windows"].items():
        low, high = window["interval_s"]
        time, value = samples(low, high)
        vi, vo, vc, vs = (value[k] for k in ("in", "out", "cap", "sw"))
        ii, il, isw, ir, io = (value[k] for k in ("vin", "lpower", "vswitch", "vrect", "vload"))
        duration = high - low
        switch_voltage = vi - vs if model["topology"] == "buck" else vs
        diode_voltage = -vs if model["topology"] == "buck" else vs - vo
        input_energy = -product_integral(time, vi, ii)
        output_energy = product_integral(time, vo, io)
        loss = (
            model["inductor_resistance_ohm"] * product_integral(time, il, il)
            + product_integral(time, vo-vc, vo-vc) / model["capacitor_esr_ohm"]
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
        capacitor_current = (vo - vc) / model["capacitor_esr_ohm"]
        values = {
            "output_mean_v": mean(time, vo), "output_min_v": float(np.min(vo)),
            "output_max_v": float(np.max(vo)), "output_pp_v": float(np.ptp(vo)),
            "inductor_mean_a": mean(time, il), "inductor_min_a": float(np.min(il)),
            "inductor_max_a": float(np.max(il)), "inductor_pp_a": float(np.ptp(il)),
            "inductor_rms_a": math.sqrt(product_integral(time, il, il) / duration),
            "capacitor_rms_a": math.sqrt(product_integral(time, capacitor_current, capacitor_current) / duration),
            "switch_peak_v": float(np.max(np.abs(switch_voltage))), "switch_peak_a": float(np.max(np.abs(isw))),
            "rectifier_reverse_peak_v": float(np.max(np.maximum(-diode_voltage, 0))),
            "input_power_w": input_energy / duration, "output_power_w": output_energy / duration,
            "loss_power_w": loss / duration, "storage_rate_w": float(storage / duration),
            "energy_relative_error": balance, "cycle_mean_relative_change": drift,
        }
        if not all(math.isfinite(value) for value in values.values()):
            raise EvidenceError("nonfinite computed converter measurement")
        measured[name] = values
    return measured
