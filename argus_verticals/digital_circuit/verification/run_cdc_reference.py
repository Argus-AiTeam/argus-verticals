"""Create and execute a finite two-clock level/reset adapter reference."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .cdc import run


def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("rtl", "design", "verification"):
        (root / directory).mkdir()
    shutil.copyfile(Path(__file__).parent / "skills/engineer_scripts/cdc_reference.sv", root / "rtl/cdc_reference.sv")
    spec = {
        "goal": "design", "top": "cdc_reference", "sources": ["rtl/cdc_reference.sv"],
        "clocks": ["clk_src", "clk_dst"],
        "resets": {
            "clk_src": {"input": "arst_n", "output": "reset_src_n", "stages": 2},
            "clk_dst": {"input": "arst_n", "output": "reset_dst_n", "stages": 2},
        },
        "crossings": {
            "status_level": {"input": "level_in", "output": "level_out", "source_clock": "clk_src",
                             "destination_clock": "clk_dst", "stages": 2},
        },
        "configurations": {
            "source_fast": {"clk_src": {"period_ticks": 10, "phase_ticks": 0}, "clk_dst": {"period_ticks": 14, "phase_ticks": 3}},
            "destination_fast": {"clk_src": {"period_ticks": 18, "phase_ticks": 4}, "clk_dst": {"period_ticks": 8, "phase_ticks": 1}},
            "coincident_edges": {"clk_src": {"period_ticks": 12, "phase_ticks": 0}, "clk_dst": {"period_ticks": 12, "phase_ticks": 0}},
        },
        "requirements": {
            "level_latency": "Source launch followed by exactly two receiving edges; no earlier-stage use.",
            "reset_assert": "Both local active-low resets assert asynchronously, including between clock edges.",
            "reset_release": "Each local reset releases only after its own two positive clock edges.",
        },
        "limitations": ["Finite stable-level tests, not pulse or coherent-bus transport, metastability, MTBF or physical CDC/RDC qualification."],
    }
    (root / "design/cdc-study.json").write_text(json.dumps(spec, indent=2) + "\n")
    (root / "verification/CDC_PLAN.json").write_text(json.dumps({"specification": "design/cdc-study.json"}) + "\n")


def run_reference(root: Path) -> None:
    prepare_reference(root)
    run(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run_reference(args.output.resolve())
    print("PASS: declared level/reset structures and finite clock/phase traces; not physical CDC/RDC qualification")


if __name__ == "__main__":
    main()
