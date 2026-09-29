"""Exercise an original two-testpoint continuity coupon, not an empty board."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .run_analysis import run_analysis


def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    shutil.copytree(Path(__file__).parent / "references/coupon", root / "design")
    (root / "pcb").mkdir()
    plan = {
        "objective": "Check an original two-testpoint continuity coupon and export its exact manufacturing geometry.",
        "requirements": [
            "ERC, DRC and schematic-board parity have no errors, warnings or exclusions.",
            "Export all copper, both solder masks and a nonempty outline at the absolute origin.",
            "Produce exactly two plated round drill hits and zero nonplated hits.",
        ],
        "limitations": [
            "An original connectivity/geometry reference, not a functional circuit or physical prototype.",
            "No field-solved SI/PI, thermal, assembly yield, fab acceptance or energizing authorization.",
        ],
        "design": {key: f"design/coupon.{suffix}" for key, suffix in (
            ("project", "kicad_pro"), ("schematic", "kicad_sch"), ("board", "kicad_pcb"),
        )},
        "checks": [
            {"kind": "erc", "max_errors": 0, "max_warnings": 0},
            {"kind": "drc", "max_errors": 0, "max_warnings": 0, "schematic_parity": True},
        ],
        "fabrication": {
            "layers": {"F.Cu": 3, "B.Cu": 2, "F.Mask": 2, "B.Mask": 2, "Edge.Cuts": 4},
            "drill_hits": {"pth": 2, "npth": 0},
        },
    }
    (root / "pcb/PLAN.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


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
