"""Prepare and run a bounded APB4 control subsystem example."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .control import run


def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("rtl", "design", "verification"):
        (root / directory).mkdir()
    shutil.copyfile(Path(__file__).parent / "skills/engineer_scripts/control_reference.sv", root / "rtl/control_reference.sv")
    spec = {
        "contract": "apb4-timer-v1", "goal": "design",
        "top": "control_reference", "sources": ["rtl/control_reference.sv"],
        "base_address": 0x40001000, "max_generic_cells": 2000,
        "configurations": {
            "compact": {"counter_width": 8, "wait_cycles": 0, "seed": 1},
            "waited": {"counter_width": 16, "wait_cycles": 2, "seed": 7},
        },
        "limitations": ["Finite APB4 single-clock control checks and generic synthesis statistics, not physical PPA or a complete SoC."],
    }
    (root / "design/control-spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    (root / "verification/CONTROL_PLAN.json").write_text(json.dumps({"specification": "design/control-spec.json"}) + "\n", encoding="utf-8")


def run_reference(root: Path) -> None:
    prepare_reference(root)
    run(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run_reference(args.output.resolve())
    print("PASS: bounded APB4 control RTL, synthesized simulation and generic-cell limits; not physical PPA")


if __name__ == "__main__":
    main()
