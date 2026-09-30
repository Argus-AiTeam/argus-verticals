"""Execute only the declared ngspice analyses from frozen project-local inputs."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from argus_verticals.hardware.shared.evidence import project_file, record

from .evidence import (
    INPUTS_DIR,
    PLAN,
    RESULTS,
    RESULTS_DIR,
    RUN_ENVIRONMENT,
    run_command,
    run_paths,
    validate_plan,
    validate_simulation,
)


def run_analysis(root: Path) -> dict:
    root = root.resolve()
    if "robustness" in record(root, PLAN):
        from .robustness import run_robustness

        return run_robustness(root)
    plan, required = validate_plan(root)
    if shutil.which("ngspice") is None:
        raise RuntimeError("ngspice is required; no simulation was performed")
    version = subprocess.run(
        ["ngspice", "--version"], capture_output=True, text=True, check=True, timeout=15,
    )
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    inputs = {}
    for relative in required:
        copy = f"{INPUTS_DIR}/{relative}"
        (root / copy).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / copy)
        inputs[relative] = copy
    results = {
        "tool_version": version.stdout + version.stderr,
        "environment": RUN_ENVIRONMENT, "inputs": inputs, "runs": [], "outputs": {},
    }
    result_path = root / RESULTS

    def save() -> None:
        result_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    save()
    for run in plan["runs"]:
        paths = run_paths(run["id"])
        (root / paths["raw"]).parent.mkdir(parents=True)
        command = run_command(run)
        row = {"id": run["id"], "command": command, "cwd": INPUTS_DIR, **paths}
        results["runs"].append(row)
        try:
            executed = subprocess.run(
                command, cwd=root / INPUTS_DIR, env={**os.environ, **RUN_ENVIRONMENT},
                capture_output=True, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            row.update(exit_code=None, error="ngspice exceeded 120 seconds")
            (root / paths["console"]).write_text(str(exc), encoding="utf-8")
            save()
            raise RuntimeError(f"{run['id']}: ngspice timed out; partial output is in {paths['log']}") from exc
        row["exit_code"] = executed.returncode
        (root / paths["console"]).write_text(
            "$ " + json.dumps(command) + "\n" + executed.stdout + executed.stderr,
            encoding="utf-8",
        )
        save()
        if executed.returncode != 0:
            raise RuntimeError(f"{run['id']}: ngspice exited {executed.returncode}; inspect {paths['log']}")
        for relative in paths.values():
            copy = relative.replace(RESULTS_DIR + "/runs/", RESULTS_DIR + "/retained/", 1)
            (root / copy).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), root / copy)
            results["outputs"][relative] = copy
        save()
    return validate_simulation(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    print(json.dumps(run_analysis(args.project), indent=2))
    print("PASS: requested numerical task accepted; a diagnosis may report noncompliance, never hardware approval")


if __name__ == "__main__":
    main()
