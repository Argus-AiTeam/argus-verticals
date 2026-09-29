"""Run independent attenuator, resistor, line and LC-matching reference studies."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

from .run_analysis import run_analysis


def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    (root / "data").mkdir()
    (root / "rf").mkdir()
    shutil.copyfile(
        Path(__file__).parent / "skills/engineer_scripts/attenuator.s2p",
        root / "data/attenuator.s2p",
    )
    base = {
        "source": "Original ideal-model reference, independently checked using scalar RF equations.",
        "validity": "Linear single-ended networks at the declared positive frequencies and real port references.",
        "limitations": ["No measured device, fixture calibration, nonlinear, noise, parasitic or full-wave claim."],
    }
    frequency = [0.5e9, 1e9, 1.5e9]
    definitions = {
        "attenuator": {**base, "kind": "touchstone", "path": "data/attenuator.s2p", "ports": ["input", "output"]},
        "twice": {"kind": "cascade", "inputs": ["attenuator", "attenuator"]},
        "resistor": {**base, "kind": "lumped", "frequency_hz": frequency, "z0_ohm": [50, 50],
                     "elements": [{"kind": "R", "connection": "series", "value_si": 50}]},
        "resistor_75": {"kind": "renormalize", "input": "resistor", "z0_ohm": [75, 75]},
        "quarter_wave": {**base, "kind": "line", "frequency_hz": frequency, "z0_ohm": [50, 50],
                         "impedance_ohm": 50, "delay_s": 0.25e-9, "loss_db": 0},
        "match": {**base, "kind": "lumped", "frequency_hz": frequency, "z0_ohm": [50, 100],
                  "elements": [
                      {"kind": "L", "connection": "series", "value_si": 50 / (2 * math.pi * 1e9)},
                      {"kind": "C", "connection": "shunt", "value_si": 1 / (2 * math.pi * 1e9 * 100)},
                  ]},
    }

    def check(identity, metric, value, tolerance=1e-9, ports=None):
        result = {
            "id": identity, "metric": metric, "statistic": "at", "at_hz": 1e9,
            "unit": "dB" if metric == "s_db" else "deg" if metric == "s_phase_deg" else "1",
            "minimum": value - tolerance, "maximum": value + tolerance,
        }
        if ports is not None:
            result["ports"] = ports
        return result

    comparisons = {
        "attenuator": [check("gain_db", "s_db", 20 * math.log10(0.5), ports=[2, 1])],
        "twice": [check("gain_db", "s_db", 20 * math.log10(0.25), ports=[2, 1])],
        "resistor": [check("reflection", "s_real", 1 / 3, ports=[1, 1]), check("transmission", "s_real", 2 / 3, ports=[2, 1])],
        "resistor_75": [check("reflection", "s_real", 0.25, ports=[1, 1]), check("transmission", "s_real", 0.75, ports=[2, 1])],
        "quarter_wave": [check("phase", "s_phase_deg", -90, ports=[2, 1]), check("magnitude", "s_magnitude", 1, ports=[2, 1])],
        "match": [check("input_match", "s_magnitude", 0, ports=[1, 1]), check("transmission", "s_magnitude", 1, ports=[2, 1]),
                  check("phase", "s_phase_deg", -45, ports=[2, 1]), check("power_bound", "sigma_max", 1),
                  check("reciprocity", "reciprocity_error", 0)],
    }
    plan = {
        "objective": "Verify six explicitly limited RF network calculations against independent circuit equations.",
        "requirements": {name: f"Verify the independent {name} reference equations at 1 GHz." for name in comparisons},
        "limitations": base["limitations"], "networks": definitions,
        "studies": [
            {"id": name, "network": name, "checks": [{**item, "requirement": name} for item in checks]}
            for name, checks in comparisons.items()
        ],
    }
    (root / "rf/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def run_reference(root: Path) -> dict[str, dict[str, float]]:
    prepare_reference(root)
    return run_analysis(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory; existing work is never overwritten")
    args = parser.parse_args()
    print(json.dumps(run_reference(args.output), indent=2))
    print("PASS: six real scikit-rf calculations, not physical measurements")


if __name__ == "__main__":
    main()
