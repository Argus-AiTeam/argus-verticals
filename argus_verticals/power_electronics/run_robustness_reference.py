"""Original operating-envelope reference with fixed design/diagnostic semantics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .run_analysis import run_analysis


def prepare_reference(root: Path, *, goal: str = "design", tight: bool = False) -> None:
    if goal not in ("diagnose", "design"):
        raise ValueError("goal must be diagnose or design")
    root.mkdir(parents=True, exist_ok=False)
    (root / "design").mkdir()
    (root / "power").mkdir()
    model = {
        "topology": "buck", "source": "Original illustrative converter, not commercial component data.",
        "validity": "Open-loop PWM, linear L/C, finite resistances and a native charge-free diode.",
        "limitations": ["No control, magnetic saturation, device charge, EMI or physical qualification."],
        "inductance_h": 100e-6, "capacitance_f": 22e-6,
        "inductor_resistance_ohm": 0.05, "capacitor_esr_ohm": 0.02,
        "switch_on_resistance_ohm": 0.02, "switch_off_resistance_ohm": 1e8,
        "diode_saturation_current_a": 1e-9, "diode_emission": 1,
        "diode_resistance_ohm": 0.02, "temperature_c": 27,
    }
    specification = {
        "goal": goal, "source": "Original finite operating samples and independently declared engineering limits.",
        "limitations": ["Finite samples only; not a full interval or probability guarantee."],
        "model": "design/buck.json",
        "conditions": {
            "input_voltage_v": 12, "duty_cycle": 0.5304, "frequency_hz": 50000,
            "load_resistance_ohm": 5, "duration_s": 0.002,
            "windows": {"settled": {"kind": "steady", "interval_s": [0.0016, 0.002]}},
        },
        "design_variables": {},
        "axes": [
            {"id": "supply", "target": "run.input_voltage_v", "unit": "V",
             "source": "Explicit demonstration source tolerance.", "values": [11.8, 12.2]},
            {"id": "capacitance", "target": "model.capacitance_f", "unit": "1",
             "source": "Explicit demonstration capacitance tolerance.", "factors": [0.8, 1.2]},
        ],
        "maximum_steps_s": [2e-7, 1e-7],
        "checks": [
            {"id": "voltage", "requirement": "regulation", "window": "settled",
             "metric": "output_mean_v", "unit": "V",
             "minimum": 5.97 if tight else 5.8, "maximum": 6.03 if tight else 6.2,
             "margin_lower": 0.001 if tight else 0.02, "margin_upper": 0.001 if tight else 0.02},
            {"id": "ripple", "requirement": "regulation", "window": "settled",
             "metric": "output_pp_v", "unit": "V", "minimum": 0, "maximum": 0.12,
             "margin_upper": 0.005},
        ],
        "convergence": [
            {"window": "settled", "metric": "output_mean_v", "max_delta": 0.005},
            {"window": "settled", "metric": "output_pp_v", "max_delta": 0.005},
        ],
    }
    design = {}
    if goal == "design":
        specification["design_variables"] = {
            "duty": {"target": "run.duty_cycle", "unit": "1",
                     "source": "Allowed fixed-duty design decision.", "minimum": 0.52, "maximum": 0.54},
        }
        design = {"duty": 0.5304}
    plan = {
        "objective": "Evaluate the complete declared converter envelope and quantify original numerical margins.",
        "requirements": {"regulation": "Every declared operating sample must meet original voltage/ripple limits and headroom."},
        "limitations": model["limitations"], "models": ["design/buck.json"],
        "robustness": {"specification": "design/operating.json", "design": design},
    }
    for relative, value in (("design/buck.json", model), ("design/operating.json", specification), ("power/PLAN.json", plan)):
        (root / relative).write_text(json.dumps(value, indent=2) + "\n")


def run_reference(root: Path, *, goal: str = "design", tight: bool = False) -> dict:
    prepare_reference(root, goal=goal, tight=tight)
    return run_analysis(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--goal", choices=("diagnose", "design"), default="design")
    parser.add_argument("--tight", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_reference(args.project, goal=args.goal, tight=args.tight), indent=2))


if __name__ == "__main__":
    main()
