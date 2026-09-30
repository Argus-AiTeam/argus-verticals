"""Calculate declared scikit-rf studies from copied inputs and retain Touchstone results."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, project_file

from .evidence import (
    INPUTS_DIR,
    OPERATION,
    RESULTS,
    RESULTS_DIR,
    result_path,
    validate_analysis,
    validate_plan,
    validate_specification,
)
from .networks import versions, write_network


def run_analysis(root: Path) -> dict:
    root = root.resolve()
    if "robustness" in validate_specification(root):
        from .robustness import run_robustness

        return run_robustness(root)
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
        "versions": versions(),
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
            write_network(path, networks[study["network"]])
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
    report = run_analysis(args.project)
    print(json.dumps(report, indent=2))
    if "task_accepted" in report:
        print("ACCEPTED: declared RF task goal; inspect ASSESSMENT.json for passed or failed original limits")
    else:
        print("PASS: declared RF network checks; no full-wave, calibration or hardware qualification claim")


if __name__ == "__main__":
    main()
