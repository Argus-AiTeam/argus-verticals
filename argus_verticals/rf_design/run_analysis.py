"""Calculate declared scikit-rf studies from copied inputs and retain Touchstone results."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
from pathlib import Path

import numpy as np
import skrf as rf

from argus_verticals.hardware.shared.evidence import EvidenceError, project_file

from .evidence import (
    INPUTS_DIR,
    OPERATION,
    RESULTS,
    RESULTS_DIR,
    result_path,
    validate_analysis,
    validate_plan,
)


def run_analysis(root: Path) -> dict[str, dict[str, float]]:
    root = root.resolve()
    _, _, required = validate_plan(root)
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    inputs = {}
    for relative in required:
        target = f"{INPUTS_DIR}/{relative}"
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / target)
        inputs[relative] = target
    result = {
        "operation": OPERATION, "status": "running",
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "scikit-rf": rf.__version__},
        "inputs": inputs, "studies": [], "outputs": {},
    }

    def save() -> None:
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        plan, networks, _ = validate_plan(root / INPUTS_DIR)
        for study in plan["studies"]:
            relative = result_path(study["id"])
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            network = networks[study["network"]]
            network.frequency.unit = "hz"
            data = network.write_touchstone(
                filename=path, return_string=True, version="2.0", form="ri",
                write_noise=False, encoding="utf-8",
                format_spec_A="{:.17g}", format_spec_B="{:.17g}", format_spec_freq="{:.17g}",
            )
            if not isinstance(data, str) or not data.strip():
                raise EvidenceError("scikit-rf did not produce Touchstone output")
            path.write_text(data, encoding="utf-8")
            retained = f"{RESULTS_DIR}/retained/{study['id']}.ts"
            (root / retained).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, root / retained)
            result["studies"].append({"id": study["id"], "network": study["network"], "path": relative})
            result["outputs"][relative] = retained
            save()
        result["status"] = "complete"
        save()
        measurements = validate_analysis(root)
    except (EvidenceError, OSError, ValueError) as exc:
        result.update(status="failed", error=str(exc))
        save()
        raise
    return measurements


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_analysis(args.project), indent=2))
    print("PASS: declared RF network checks; no full-wave, calibration or hardware qualification claim")


if __name__ == "__main__":
    main()
