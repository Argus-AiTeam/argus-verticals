"""Original native startup/load-step studies with independent averaged CCM equations."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .model import METRICS
from .run_analysis import run_analysis


def reference_voltage(model: dict, run: dict, load: float) -> float:
    """Averaged constant-current approximation, not a transient solver."""
    if model["temperature_c"] != 27:
        raise ValueError("this independent reference assumes 27 C nominal diode temperature")
    duty, source = run["duty_cycle"], run["input_voltage_v"]
    lower, upper = 0.0, source / (1 - duty)
    for _ in range(80):
        voltage = (lower + upper) / 2
        current = voltage / load / (1 if model["topology"] == "buck" else 1 - duty)
        diode = (
            model["diode_emission"] * 8.617333262145e-5 * 300.15
            * math.log1p(current / model["diode_saturation_current_a"])
            + model["diode_resistance_ohm"] * current
        )
        loss = current * (model["inductor_resistance_ohm"] + duty * model["switch_on_resistance_ohm"])
        difference = (
            duty * source - loss - (1 - duty) * diode - voltage
            if model["topology"] == "buck" else source - loss - (1 - duty) * (voltage + diode)
        )
        if difference > 0:
            lower = voltage
        else:
            upper = voltage
    return (lower + upper) / 2


def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    (root / "design").mkdir()
    (root / "power").mkdir()
    base = {
        "source": "Original illustrative switching-converter constants, not commercial device data.",
        "validity": "Open-loop PWM, linear L/C, resistive switch, native memoryless diode, resistive load.",
        "limitations": ["No device charge, reverse recovery, control loop, saturation, EMI, thermal feedback or physical operation."],
        "inductance_h": 100e-6, "inductor_resistance_ohm": 0.05,
        "capacitor_esr_ohm": 0.02, "switch_on_resistance_ohm": 0.02,
        "switch_off_resistance_ohm": 1e8, "diode_saturation_current_a": 1e-9,
        "diode_emission": 1, "diode_resistance_ohm": 0.02, "temperature_c": 27,
    }
    plan = {
        "objective": "Check actual switched Buck/Boost startup, pre/post-load steady behavior and time-step sensitivity.",
        "requirements": {}, "limitations": base["limitations"], "models": [], "runs": [], "convergence": [],
    }
    for topology, vin, load, capacitance in (("buck", 12, 5, 22e-6), ("boost", 6, 10, 10e-6)):
        model = {**base, "topology": topology, "capacitance_f": capacitance}
        relative = f"design/{topology}.json"
        (root / relative).write_text(json.dumps(model, indent=2) + "\n")
        plan["models"].append(relative)
        requirement = f"{topology}_behavior"
        plan["requirements"][requirement] = "Native startup, real load doubling and CCM averages agree with bounded independent circuit reasoning."
        run = {
            "model": relative, "input_voltage_v": vin, "duty_cycle": 0.5, "frequency_hz": 50000,
            "load_resistance_ohm": load, "duration_s": 0.004,
            "load_step": {"time_s": 0.002, "transition_s": 0.00002, "resistance_ohm": load / 2},
            "windows": {
                "startup": {"kind": "startup", "interval_s": [0.000001, 0.0015]},
                "before": {"kind": "steady", "interval_s": [0.0016, 0.0019]},
                "transition": {"kind": "load_step", "interval_s": [0.00198, 0.0024]},
                "after": {"kind": "steady", "interval_s": [0.003, 0.004]},
            },
            "checks": [],
        }

        def check(window, metric, low, high):
            run["checks"].append({
                "id": f"{window}_{metric}", "requirement": requirement, "window": window,
                "metric": metric, "unit": METRICS[metric], "minimum": low, "maximum": high,
            })

        before = reference_voltage(model, run, load)
        after = reference_voltage(model, run, load / 2)
        check("startup", "output_max_v", before, 2 * before)
        check("transition", "output_min_v", after / 2, before)
        for window, voltage, resistance in (("before", before, load), ("after", after, load / 2)):
            tolerance = 0.02 if topology == "buck" else 0.1
            check(window, "output_mean_v", voltage - tolerance, voltage + tolerance)
            current = voltage / resistance / (1 if topology == "buck" else 1 - run["duty_cycle"])
            on_voltage = vin - current * (model["inductor_resistance_ohm"] + model["switch_on_resistance_ohm"])
            if topology == "buck":
                on_voltage -= voltage
            ripple = on_voltage * run["duty_cycle"] / run["frequency_hz"] / model["inductance_h"]
            check(window, "inductor_pp_a", ripple - 0.025, ripple + 0.025)
            check(window, "inductor_min_a", 0.05, current)
            check(window, "energy_relative_error", 0, 1e-3)
        for name, step in (("coarse", 2e-7), ("fine", 1e-7)):
            plan["runs"].append({**run, "id": f"{topology}_{name}", "max_step_s": step})
        for window, metric, limit in (
            ("startup", "output_max_v", 0.02), ("transition", "output_min_v", 0.02),
            ("before", "output_mean_v", 0.01), ("before", "output_pp_v", 0.01),
            ("after", "output_mean_v", 0.01), ("after", "output_pp_v", 0.01),
            ("after", "inductor_pp_a", 0.01),
        ):
            plan["convergence"].append({
                "coarse": f"{topology}_coarse", "fine": f"{topology}_fine",
                "window": window, "metric": metric, "max_delta": limit,
            })
    (root / "power/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n")


def run_reference(root: Path) -> dict:
    prepare_reference(root)
    return run_analysis(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_reference(args.project), indent=2))


if __name__ == "__main__":
    main()
