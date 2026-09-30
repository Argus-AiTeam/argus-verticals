"""Run a finite L-match tolerance study with explicit sampled-band requirements."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .run_analysis import run_analysis


def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    (root / "design").mkdir()
    (root / "rf").mkdir()
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
    spec = {
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
    }
    plan = {
        "objective": "Assess original sampled-band L-match limits across every declared component combination.",
        "requirements": {"band": "Original matching, transmission, passivity and headroom limits must hold for every sampled case."},
        "limitations": limitations,
        "robustness": {"specification": "design/rf-study.json", "design": {}},
    }
    for path, value in (("design/rf-study.json", spec), ("rf/PLAN.json", plan)):
        (root / path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


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
