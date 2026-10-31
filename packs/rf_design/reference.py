"""Write an RF reference project with independently known answers into a new directory and run it.

Default: six analytic network studies (attenuator, its cascade, series resistor, the resistor
renormalized to 75 ohms, quarter-wave line, 50-to-100 ohm L-match). --robustness: the L-match
across every +/-5 percent L/C combination plus nominal, on a 5-point grid and its 9-point
refinement. Runs evidence.py from this folder with the same Python, so numpy and scikit-rf must
be installed there. Adapted from Argus rf_design run_reference and run_robustness_reference.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

ATTENUATOR = """! Original synthetic matched attenuator; voltage-wave transmission is 0.5.
! This file is an analytic model, not a VNA measurement.
# GHz S RI R 50
0.5 0 0 0.5 0 0.5 0 0 0
1.0 0 0 0.5 0 0.5 0 0 0
1.5 0 0 0.5 0 0.5 0 0 0
"""


def write(root: Path, relative: str, value: dict) -> None:
    (root / relative).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def prepare_networks(root: Path) -> None:
    (root / "data").mkdir()
    (root / "data/attenuator.s2p").write_text(ATTENUATOR, encoding="utf-8")
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
    write(root, "rf/PLAN.json", {
        "objective": "Verify six explicitly limited RF network calculations against independent circuit equations.",
        "requirements": {name: f"Verify the independent {name} reference equations at 1 GHz." for name in comparisons},
        "limitations": base["limitations"], "networks": definitions,
        "studies": [
            {"id": name, "network": name, "checks": [{**item, "requirement": name} for item in checks]}
            for name, checks in comparisons.items()
        ],
    })


def prepare_robustness(root: Path) -> None:
    (root / "design").mkdir()
    inductance, capacitance = 50/(2*math.pi*1e9), 1/(2*math.pi*1e9*100)
    source = "Original ideal lossless 50-to-100 ohm L-match; not measured component or fixture data."
    limitations = ["Finite declared samples only; no parasitics, calibration, full-wave, statistical yield or physical qualification."]
    checks = [
        {"id": "reflection", "metric": "s_magnitude", "ports": [1, 1], "statistic": "max",
         "window_hz": [0.8e9, 1.2e9], "unit": "1", "minimum": 0, "maximum": 0.25, "margin_upper": 0.01},
        {"id": "transmission", "metric": "s_magnitude", "ports": [2, 1], "statistic": "min",
         "window_hz": [0.8e9, 1.2e9], "unit": "1", "minimum": 0.97, "maximum": 1.000000001, "margin_lower": 0.002},
        {"id": "passivity", "metric": "sigma_max", "statistic": "max",
         "window_hz": [0.8e9, 1.2e9], "unit": "1", "minimum": 0, "maximum": 1.000000001},
    ]
    write(root, "design/rf-study.json", {
        "goal": "design", "source": source, "limitations": limitations,
        "networks": {"match": {
            "kind": "lumped", "source": source, "validity": "Ideal lumped small-signal components on explicit frequency samples.",
            "limitations": limitations, "frequency_hz": [0.8e9, 0.9e9, 1e9, 1.1e9, 1.2e9], "z0_ohm": [50, 100],
            "elements": [
                {"kind": "L", "connection": "series", "value_si": inductance},
                {"kind": "C", "connection": "shunt", "value_si": capacitance},
            ],
        }},
        "parameters": {
            name: {"network": "match", "element": index, "nominal": value,
                   "minimum": value/4, "maximum": value*4, "unit": unit, "source": source}
            for name, index, value, unit in (("series_l", 1, inductance, "H"), ("shunt_c", 2, capacitance, "F"))
        },
        "design_variables": {},
        "axes": [
            {"id": name+"_tolerance", "parameter": name, "unit": "1", "factors": [0.95, 1.05],
             "source": "Explicit independent +/-5 percent reference samples, not a probability distribution."}
            for name in ("series_l", "shunt_c")
        ],
        "studies": [{"id": "matching", "network": "match",
                     "checks": [{**check, "requirement": "band", "max_delta": 0.0001} for check in checks]}],
    })
    write(root, "rf/PLAN.json", {
        "objective": "Assess original sampled-band L-match limits across every declared component combination.",
        "requirements": {"band": "Original matching, transmission, passivity and headroom limits must hold for every sampled case."},
        "limitations": limitations,
        "robustness": {"specification": "design/rf-study.json", "design": {}},
    })


def main() -> int:
    parser = argparse.ArgumentParser(prog="reference.py", description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="new directory; existing work is never overwritten")
    parser.add_argument("--robustness", action="store_true", help="the L-match tolerance study instead")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "rf").mkdir()
    (prepare_robustness if args.robustness else prepare_networks)(root)
    evidence = Path(__file__).resolve().with_name("evidence.py")
    return subprocess.run([sys.executable, str(evidence), "run", "--project-root", str(root)]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
