"""Run only selected native PCB checks and exports from independent copied inputs."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, project_file

from . import native
from .design import INPUTS_DIR, RESULTS, RESULTS_DIR, validate_plan
from .evidence import validate_verification


def run_analysis(root: Path) -> dict:
    root = root.resolve()
    plan, required = validate_plan(root)
    version = native.version()
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    inputs = {}
    for relative in required:
        target = f"{INPUTS_DIR}/{relative}"
        (root / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / target)
        inputs[relative] = target
    result = {
        "operation": "kicad-cli", "status": "running", "kicad_version": version,
        "inputs": inputs, "commands": [], "outputs": {},
    }

    def save(commands=None) -> None:
        if commands is not None:
            result["commands"] = commands
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        frozen_plan, _ = validate_plan(root / INPUTS_DIR)
        if frozen_plan != plan:
            raise EvidenceError("plan changed while copying inputs")
        output = root / RESULTS_DIR / "native"
        native.execute(root / INPUTS_DIR, plan, output, save=save)
        for path in native.output_paths(plan, output):
            retained = f"{RESULTS_DIR}/retained/{path.relative_to(output).as_posix()}"
            (root / retained).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, root / retained)
            result["outputs"][path.relative_to(root).as_posix()] = retained
        result["status"] = "complete"
        save()
        measured = validate_verification(root)
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
    print("PASS: selected native PCB checks/exports only; no physical qualification or manufacture approval")


if __name__ == "__main__":
    main()
