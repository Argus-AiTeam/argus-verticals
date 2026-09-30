"""Check an original four-layer continuity coupon with freshly filled copper."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .run_analysis import run_analysis
from .run_reference import prepare_reference as prepare_coupon


def prepare_reference(root: Path) -> None:
    prepare_coupon(root)
    shutil.copyfile(
        Path(__file__).parent / "references/four-layer-zones.kicad_pcb",
        root / "design/coupon.kicad_pcb",
    )
    path = root / "pcb/PLAN.json"
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["objective"] = "Refill copied four-layer copper, then check and export that same board without changing the original."
    plan["requirements"].append("Discard old zone fills; preserve original outlines, nets, pads and project settings.")
    plan["limitations"].append("Continuity coupon only; the four same-net planes are not a production stackup or SI/PI result.")
    plan["zone_refill"] = True
    plan["fabrication"]["layers"].update({"F.Cu": 3, "In1.Cu": 3, "In2.Cu": 3, "B.Cu": 3})
    path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")


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
