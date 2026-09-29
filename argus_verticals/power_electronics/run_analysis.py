"""Run selected native converter studies without replacing previous results."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, current_files, project_file

from . import native
from .evidence import validate_simulation
from .model import INPUTS_DIR, RESULTS, RESULTS_DIR, validate_plan


def run_analysis(root: Path) -> dict[str, dict]:
    root = root.resolve()
    plan, models, inputs = validate_plan(root)
    version = native.version()
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    result = {
        "operation": "ngspice-converter", "status": "running", "ngspice_version": version,
        "inputs": {p: f"{INPUTS_DIR}/{p}" for p in inputs}, "outputs": {}, "runs": [],
    }

    def save():
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for relative, copy in result["inputs"].items():
            (root / copy).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), root / copy)
        for run in plan["runs"]:
            row = {"id": run["id"]}
            result["runs"].append(row)

            def save_command(command):
                row["execution"] = command
                save()

            native.execute(models[run["model"]], run, root / RESULTS_DIR / "native" / run["id"], save=save_command)
            for name in native.FILES:
                source = f"{RESULTS_DIR}/native/{run['id']}/{name}"
                copy = f"{RESULTS_DIR}/retained/{run['id']}/{name}"
                (root / copy).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(project_file(root, source), root / copy)
                result["outputs"][source] = copy
            save()
        current_files(root, result, inputs)
        result["status"] = "complete"
        save()
        return validate_simulation(root)
    except (EvidenceError, OSError) as exc:
        result.update(status="failed", error=str(exc))
        save()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_analysis(args.project), indent=2))


if __name__ == "__main__":
    main()
