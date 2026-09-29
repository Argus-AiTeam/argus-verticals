"""Build a verified single-clock iCE40 project; never program a device."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from argus_verticals.digital_circuit.verification.evidence import project_file

from .evidence import (
    IMPLEMENTATION_OUTPUTS,
    flow_commands,
    implementation_inputs,
    validate_implementation,
    validate_verification,
)


def run_implementation(root: Path) -> None:
    target = validate_verification(root)
    commands = flow_commands(target)
    for command in commands.values():
        if shutil.which(command[0]) is None:
            raise RuntimeError(f"{command[0]} is required; no implementation was performed")
    input_files = {relative: project_file(root, relative) for relative in implementation_inputs(root, target)}
    destination = root / "implementation"
    destination.mkdir(exist_ok=False)
    copies = {}
    for relative, source in input_files.items():
        snapshot = "implementation/inputs/" + relative
        (root / snapshot).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, root / snapshot)
        copies[relative] = snapshot
    executions = {}
    for name, command in commands.items():
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=600)
        log = f"implementation/{name}.log"
        # icepack is normally silent; preserve the executed argv as well as its output.
        (root / log).write_text("$ " + json.dumps(command) + "\n" + result.stdout + result.stderr)
        executions[name] = {"command": command, "exit_code": result.returncode, "log": log}
        (destination / "BUILD.json").write_text(json.dumps({"inputs": copies, "commands": executions}, indent=2) + "\n")
        result.check_returncode()
    outputs = {}
    for relative in IMPLEMENTATION_OUTPUTS:
        snapshot = "implementation/outputs/" + Path(relative).name
        (root / snapshot).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), root / snapshot)
        outputs[relative] = snapshot
    (destination / "BUILD.json").write_text(json.dumps({"inputs": copies, "commands": executions, "outputs": outputs}, indent=2) + "\n")
    validate_implementation(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    run_implementation(args.project.resolve())
    print("PASS: constrained iCE40 implementation; board programming and measurements were not performed")


if __name__ == "__main__":
    main()
