"""Native loaded-RC and diode studies with independent linear/Shockley expectations."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .run_analysis import run_analysis


def diode_voltage(temperature_c: float, current: float = 0.001) -> float:
    temperature, nominal, k = temperature_c + 273.15, 300.15, 8.617333262145e-5
    saturation = 1e-12 * (temperature/nominal)**3 * math.exp(1.11/k * (1/nominal-1/temperature))
    return k * temperature * math.log1p(current/saturation)


def prepare_reference(root: Path, *, goal: str = "design", tight: bool = False) -> None:
    if goal not in ("design", "diagnose"):
        raise ValueError("goal must be design or diagnose")
    root.mkdir(parents=True, exist_ok=False)
    for name in ("design", "benches", "analog"):
        (root / name).mkdir()
    parameters = {
        "resistance": (1000, 500, 2000, "ohm"), "capacitance": (100e-9, 50e-9, 200e-9, "F"),
        "load": (10000, 5000, 20000, "ohm"), "input_v": (1, 0.5, 2, "V"),
        "temp_c": (27, -20, 100, "degC"),
    }
    (root / "design/parameters.inc").write_text(
        "* Original nominal parameters; not measured parts\n"
        + "".join(f".param {name}={values[0]:.17g}\n" for name, values in parameters.items())
    )
    (root / "design/circuit.inc").write_text(
        "Vin in 0 DC {input_v} AC 1\nRseries in out {resistance}\n"
        "Cshunt out 0 {capacitance} IC=0\nRload out 0 {load}\n"
        "Idiode 0 diode DC 0.001\nDreference diode 0 DREF\n"
        ".model DREF D(Is=1e-12 N=1 Rs=0 Cjo=0 Tt=0 EG=1.11 XTI=3 TNOM=27)\n"
        ".temp {temp_c}\n.options tnom=27\n"
    )
    methods = {"bias": ".op", "transfer": ".dc Vin 0 2 0.1",
               "frequency": ".ac dec 80 10 100000", "step": ".tran 1u 1m 0 1u uic"}
    kinds = {"bias": "op", "transfer": "dc", "frequency": "ac", "step": "tran"}
    for identity, directive in methods.items():
        (root / f"benches/{identity}.cir").write_text(
            "Original loaded RC and independent diode example\n"
            '.include "design/parameters.inc"\n.include "design/circuit.inc"\n'
            ".save v(in) v(out) v(diode)\n" + directive + "\n.end\n"
        )

    def check(identity, requirement, statistic, unit, low, high, delta, **fields):
        return {"id": identity, "requirement": requirement, "vector": "v(out)", "component": "real",
                "statistic": statistic, "unit": unit, "minimum": low, "maximum": high,
                "max_delta": delta, **fields}

    checks = {
        "bias": [
            check("dc_level", "bias", "point", "V", 0.85, 0.96, 1e-4, margin_lower=0.005, margin_upper=0.005),
            check("diode", "temperature", "point", "V", 0.4, 0.7, 1e-4, vector="v(diode)",
                  margin_lower=0.005, margin_upper=0.005),
        ],
        "transfer": [check("midpoint", "transfer", "at", "V", 0.4, 0.49, 1e-5, at=0.5)],
        "frequency": [
            check("gain", "frequency", "at", "1", 0.77 if tight else 0.70, 0.80 if tight else 0.88, 2e-4,
                  at=1000, denominator="v(in)", component="magnitude", margin_lower=0.001, margin_upper=0.001),
            check("phase", "frequency", "at", "deg", -36, -22, 0.03, at=1000,
                  denominator="v(in)", component="phase_deg", margin_lower=0.1, margin_upper=0.1),
            check("edge", "frequency", "crossing", "Hz", 1800, 3800, 2,
                  window=[100, 10000], denominator="v(in)", component="magnitude", level=0.5, direction="falling"),
        ],
        "step": [
            check("response", "step", "at", "V", 0.50, 0.72, 1e-4, at=0.0001),
            check("rise", "step", "crossing", "s", 50e-6, 110e-6, 2e-7,
                  window=[1e-8, 0.0005], level=0.5, direction="rising"),
        ],
    }
    spec = {
        "goal": goal, "source": "Original finite study with limits declared before native execution.",
        "limitations": ["Linear RC and illustrative memoryless diode; no process, noise or physical-device guarantee.",
                        "DC sweeps Vin explicitly; an OP compares solver tolerance, not an axis grid."],
        "parameter_file": "design/parameters.inc",
        "parameters": {
            name: {"nominal": values[0], "minimum": values[1], "maximum": values[2], "unit": values[3],
                   "source": "Original illustrative model range, not a commercial device rating."}
            for name, values in parameters.items()
        },
        "design_variables": {} if goal == "diagnose" else {
            "resistance": {"parameter": "resistance", "minimum": 800, "maximum": 1200,
                           "source": "Allowed single common resistance choice."},
        },
        "axes": [
            {"id": "r", "parameter": "resistance", "unit": "1", "factors": [0.9, 1.1], "source": "Declared resistor samples."},
            {"id": "c", "parameter": "capacitance", "unit": "1", "factors": [0.9, 1.1], "source": "Declared capacitor samples."},
            {"id": "load", "parameter": "load", "unit": "ohm", "values": [8000, 12000], "source": "Declared load samples."},
            {"id": "temperature", "parameter": "temp_c", "unit": "degC", "values": [0, 60], "source": "Diode model temperature only."},
        ],
        "relative_tolerances": [1e-4, 1e-6],
        "analyses": [{"id": identity, "kind": kinds[identity], "netlist": f"benches/{identity}.cir",
                      "checks": checks[identity]} for identity in methods],
    }
    (root / "design/operating.json").write_text(json.dumps(spec, indent=2) + "\n")
    plan = {
        "objective": "Assess all original loaded-RC and diode samples without relaxing requirements.",
        "requirements": {"bias": "Loaded DC level.", "transfer": "DC transfer at 0.5 V.",
                         "frequency": "Declared gain, phase and 0.5 V/V band edge, not a varying -3 dB definition.",
                         "step": "Zero-initial-condition step response.", "temperature": "Diode forward voltage over temperature."},
        "limitations": ["Finite samples and model equations are not physical qualification."],
        "models": {
            path: {"kind": "testbench" if path.startswith("benches/") else "device",
                   "source": "Original hand-written passive network and explicit Shockley diode.",
                   "validity": "Declared parameter ranges and native analyses.",
                   "limitations": ["No real device characterization, parasitics or electrothermal feedback."]}
            for path in ["design/parameters.inc", "design/circuit.inc", *(f"benches/{identity}.cir" for identity in methods)]
        },
        "robustness": {"specification": "design/operating.json", "design": {} if goal == "diagnose" else {"resistance": 1000}},
    }
    (root / "analog/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--goal", choices=("design", "diagnose"), default="design")
    parser.add_argument("--tight", action="store_true", help="original narrower gain requirement; nominal passes, some corners fail")
    args = parser.parse_args()
    prepare_reference(args.output, goal=args.goal, tight=args.tight)
    print(json.dumps(run_analysis(args.output), indent=2))


if __name__ == "__main__":
    main()
