"""Execute RC and finite-gain feedback examples against independent equations."""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path

from .run_analysis import run_analysis


def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("models", "benches", "analog"):
        (root / directory).mkdir()
    examples = Path(__file__).parent / "skills/engineer_scripts"
    for source in examples.iterdir():
        destination = "models" if source.suffix == ".inc" else "benches"
        if source.suffix in {".inc", ".cir"}:
            shutil.copyfile(source, root / destination / source.name)
    models = {}
    for directory in ("models", "benches"):
        for source in sorted((root / directory).iterdir()):
            models[source.relative_to(root).as_posix()] = {
                "kind": "testbench" if directory == "benches" else "ideal" if source.stem == "rc" else "behavioral",
                "source": "Hand-written reference; independently predicted by RC and one-pole feedback equations.",
                "validity": "Linear model, 27 C, and the explicit excitation/sweep ranges in the deck.",
                "limitations": ["No component parasitics, supply rails, saturation, slew limit, noise or process qualification."],
            }
    cutoff = 1 / (2 * math.pi * 1000 * 100e-9)
    gain = 100000 / (1 + 100000 / 11)
    bandwidth = 10 * (1 + 100000 / 11)

    def check(identity, requirement, statistic, unit, low, high, **fields):
        return {
            "id": identity, "requirement": requirement, "vector": "v(out)",
            "component": "real", "statistic": statistic, "unit": unit,
            "minimum": low, "maximum": high, **fields,
        }

    plan = {
        "objective": "Check ideal RC and finite-gain one-pole feedback responses, not hardware qualification.",
        "requirements": {
            "rc_dc": "The RC passes DC without load-induced attenuation.",
            "rc_bandwidth": "RC bandwidth agrees with 1/(2*pi*R*C).",
            "rc_step": "RC time constant agrees with R*C.",
            "amplifier_gain": "Feedback gain reflects finite open-loop gain, not an ideal infinite-gain assumption.",
            "amplifier_bandwidth": "Closed-loop bandwidth agrees with the explicitly one-pole model.",
        },
        "limitations": ["These independent equations apply only to the stated ideal/behavioral models."],
        "models": models,
        "runs": [
            {"id": "rc_op", "kind": "op", "netlist": "benches/rc_op.cir", "checks": [
                check("bias", "rc_dc", "point", "V", 0.999, 1.001),
            ]},
            {"id": "rc_dc", "kind": "dc", "netlist": "benches/rc_dc.cir", "checks": [
                check("midpoint", "rc_dc", "at", "V", 0.499, 0.501, at=0.5),
            ]},
            {"id": "rc_ac", "kind": "ac", "netlist": "benches/rc_ac.cir", "checks": [
                check("cutoff", "rc_bandwidth", "crossing", "Hz", cutoff * 0.997, cutoff * 1.003,
                      denominator="v(in)", component="magnitude", level=1 / math.sqrt(2),
                      direction="falling", window=[100, 10000]),
                check("phase", "rc_bandwidth", "at", "deg", -45.1, -44.9,
                      denominator="v(in)", component="phase_deg", at=cutoff),
            ]},
            {"id": "rc_tran", "kind": "tran", "netlist": "benches/rc_tran.cir", "checks": [
                check("time_constant", "rc_step", "crossing", "s", 99e-6, 101e-6,
                      level=1 - math.exp(-1), direction="rising", window=[1e-8, 0.0005]),
            ]},
            {"id": "amplifier_op", "kind": "op", "netlist": "benches/amplifier_op.cir", "checks": [
                check("bias", "amplifier_gain", "point", "V", gain * 0.1 * 0.999, gain * 0.1 * 1.001),
            ]},
            {"id": "amplifier_ac", "kind": "ac", "netlist": "benches/amplifier_ac.cir", "checks": [
                check("gain", "amplifier_gain", "at", "1", 10.98, 11.01,
                      denominator="v(in)", component="magnitude", at=1000),
                check("bandwidth", "amplifier_bandwidth", "crossing", "Hz", bandwidth * 0.997, bandwidth * 1.003,
                      denominator="v(in)", component="magnitude", level=gain / math.sqrt(2),
                      direction="falling", window=[10000, 1000000]),
            ]},
        ],
    }
    (root / "analog/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


def run_reference(root: Path) -> dict[str, dict[str, float]]:
    prepare_reference(root)
    return run_analysis(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory; existing work is never overwritten")
    args = parser.parse_args()
    print(json.dumps(run_reference(args.output.resolve()), indent=2))
    print("PASS: six native analyses; only the stated ideal/behavioral circuit models were checked")


if __name__ == "__main__":
    main()
