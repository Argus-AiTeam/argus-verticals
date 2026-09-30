"""Preserve original package models and execute genuine native thermal studies."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, project_file

from . import native
from .evidence import validate_thermal
from .model import INPUTS_DIR, RESULTS, RESULTS_DIR, temperature_offset, validate_plan


def run_analysis(root: Path) -> dict[str, dict]:
    root = root.resolve()
    plan, _, required = validate_plan(root)
    versions = native.versions()
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    copies = {}
    for relative in required:
        target = f"{INPUTS_DIR}/{relative}"
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / target)
        copies[relative] = target
    result = {"operation": "gmsh+calculix", "status": "running", "versions": versions, "inputs": copies, "runs": [], "outputs": {}}

    def save() -> None:
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        frozen, models, _ = validate_plan(root / INPUTS_DIR)
        if frozen != plan:
            raise EvidenceError("package plan changed while inputs were copied")
        for run in plan["runs"]:
            row = {"id": run["id"], "temperature_reference_k": temperature_offset(run), "commands": []}
            result["runs"].append(row)

            def save_commands(commands) -> None:
                row["commands"] = commands
                save()

            output = root / RESULTS_DIR / "native" / run["id"]
            native.execute(models[run["model"]], run, output, save=save_commands)
            for name in native.FILES:
                retained = f"{RESULTS_DIR}/retained/{run['id']}/{name}"
                (root / retained).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(output / name, root / retained)
                result["outputs"][f"{RESULTS_DIR}/native/{run['id']}/{name}"] = retained
            save()
        result["status"] = "complete"
        save()
        measured = validate_thermal(root)
    except (EvidenceError, OSError, UnicodeError) as exc:
        result.update(status="failed", error=str(exc))
        save()
        raise
    return measured


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_analysis(args.project), indent=2))
    print("PASS: selected ideal bonded-stack thermal model only; no package qualification claim")


if __name__ == "__main__":
    main()
