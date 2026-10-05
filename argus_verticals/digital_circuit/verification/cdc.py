"""Execute and replay original-input-bound CDC/reset adapter studies."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    command_result,
    current_files,
    project_file,
    record,
)

from . import cdc_simulation
from .cdc_model import ASSESSMENT, DIRECTORY, LIMITS, RESULTS, resolve, structure


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _commands(spec: dict) -> list[tuple[str, list[str]]]:
    script = "read_verilog -sv -noautowire " + " ".join(spec["sources"])
    script += f"; hierarchy -check -top {spec['top']}; proc; flatten; opt_clean; check -assert; write_json {DIRECTORY}/netlist.json"
    commands = [("yosys", ["yosys", "-Q", "-T", "-p", script])]
    for name in spec["configurations"]:
        commands += [
            (f"{name}.compile", ["iverilog", "-g2012", "-s", "cdc_tb", "-o", f"{DIRECTORY}/{name}.vvp",
                                *spec["sources"], f"{DIRECTORY}/{name}.sv"]),
            (f"{name}.simulate", ["vvp", f"{DIRECTORY}/{name}.vvp"]),
        ]
    return commands


def _execute(root: Path, spec: dict, result: dict) -> None:
    deadline = time.monotonic() + 180
    for name, configuration in spec["configurations"].items():
        frames = cdc_simulation.stimulus(spec, configuration)
        (root / DIRECTORY / f"{name}.sv").write_text(cdc_simulation.testbench(spec, frames), encoding="utf-8")
    for name, command in _commands(spec):
        log = f"{DIRECTORY}/{name}.log"
        row = {"step": name, "command": command, "exit_code": None, "log": log}
        result["commands"].append(row)
        _write(root / RESULTS, result)
        timeout = min(30, deadline - time.monotonic())
        if timeout <= 0:
            raise EvidenceError("CDC native study exceeded its 180-second execution budget")
        with (root / log).open("w", encoding="utf-8") as stream:
            stream.write("$ " + json.dumps(command) + "\n")
            stream.flush()
            try:
                completed = subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise EvidenceError(f"{name}: native command could not finish: {exc}") from exc
        row["exit_code"] = completed.returncode
        _write(root / RESULTS, result)
        if completed.returncode != 0:
            raise EvidenceError(f"{name}: native command exited {completed.returncode}; retained {log}")
        if sum(p.stat().st_size for p in (root / DIRECTORY).iterdir() if p.is_file()) > 128 * 1024 * 1024:
            raise EvidenceError("CDC generated output exceeded 128 MiB")


def _assessment(root: Path, spec: dict) -> dict:
    structural = structure(spec, record(root, f"{DIRECTORY}/netlist.json"))
    simulations = {
        name: cdc_simulation.measure(spec, configuration, project_file(root, f"{DIRECTORY}/{name}.simulate.log").read_text(encoding="utf-8"))
        for name, configuration in spec["configurations"].items()
    }
    passed = structural["passed"] and all(row["passed"] for row in simulations.values())
    return {
        "goal": spec["goal"], "status": "passed" if passed else "failed",
        "conclusion_valid": True, "task_accepted": passed or spec["goal"] == "diagnose",
        "scope": LIMITS, "structure": structural, "simulations": simulations,
    }


def run(root: Path) -> dict:
    root = root.resolve()
    spec, inputs = resolve(root)
    for tool in ("yosys", "iverilog", "vvp"):
        if shutil.which(tool) is None:
            raise EvidenceError(f"{tool} is required for actual CDC/reset execution")
    destination = root / DIRECTORY
    destination.mkdir(parents=True, exist_ok=False)
    copies = {}
    for relative in inputs:
        snapshot = f"{DIRECTORY}/inputs/{relative}"
        target = root / snapshot
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), target)
        copies[relative] = snapshot
    result = {"operation": "yosys-icarus-cdc-reset", "status": "running", "inputs": copies, "commands": [], "outputs": {}}
    _write(root / RESULTS, result)
    try:
        if resolve(root)[0] != spec:
            raise EvidenceError("CDC original specification changed during input capture")
        current_files(root, result, inputs)
        _execute(root, spec, result)
        assessment = _assessment(root, spec)
        _write(root / ASSESSMENT, assessment)
        for path in sorted(destination.iterdir()):
            if path.is_file() and path.name != "RESULTS.json":
                relative = path.relative_to(root).as_posix()
                copy = f"{DIRECTORY}/retained/{path.name}"
                (root / copy).parent.mkdir(exist_ok=True)
                shutil.copyfile(path, root / copy)
                result["outputs"][relative] = copy
        current_files(root, result, inputs)
        result["status"] = "complete"
        _write(root / RESULTS, result)
        if not assessment["task_accepted"]:
            raise EvidenceError("CDC design violates the original structural or finite-trace requirements; diagnosis retained")
        return assessment
    except EvidenceError as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        _write(root / RESULTS, result)
        raise


def validate(root: Path, *, require_pass: bool = False) -> dict:
    root = root.resolve()
    spec, inputs = resolve(root)
    result = record(root, RESULTS)
    if result.get("operation") != "yosys-icarus-cdc-reset" or result.get("status") != "complete":
        raise EvidenceError("CDC needs a complete native execution record")
    if result.get("inputs") != {p: f"{DIRECTORY}/inputs/{p}" for p in inputs}:
        raise EvidenceError("CDC input copies must match the entire original specification/source list")
    current_files(root, result, inputs)
    paths = [ASSESSMENT, f"{DIRECTORY}/netlist.json"]
    for name in spec["configurations"]:
        paths += [f"{DIRECTORY}/{name}.{extension}" for extension in ("sv", "vvp")]
    commands = result.get("commands")
    expected_commands = _commands(spec)
    if not isinstance(commands, list) or len(commands) != len(expected_commands):
        raise EvidenceError("CDC commands must cover native extraction and every original configuration")
    for row, (step, command) in zip(commands, expected_commands):
        log = f"{DIRECTORY}/{step}.log"
        if not isinstance(row, dict) or row.get("step") != step or row.get("command") != command or row.get("log") != log:
            raise EvidenceError("CDC command, configuration or log differs from the declared native flow")
        command_result(root, row)
        paths.append(log)
    outputs = {p: f"{DIRECTORY}/retained/{Path(p).name}" for p in paths}
    if result.get("outputs") != outputs:
        raise EvidenceError("CDC must retain every generated model, executable, trace, testbench and assessment")
    current_files(root, result, paths, field="outputs")
    measured = _assessment(root, spec)
    if record(root, ASSESSMENT) != measured or not measured["task_accepted"]:
        raise EvidenceError("CDC saved assessment differs from raw structural/trace evidence or is not accepted")
    if require_pass and measured["status"] != "passed":
        raise EvidenceError("CDC diagnosis may finish with findings, but a composed design verification must pass")
    with tempfile.TemporaryDirectory(prefix="argus-cdc-check-") as directory:
        temporary = Path(directory)
        for relative in inputs:
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), target)
        fresh = run(temporary)
        if fresh != measured or record(temporary, f"{DIRECTORY}/netlist.json") != record(root, f"{DIRECTORY}/netlist.json"):
            raise EvidenceError("CDC saved native model or measurements disagree with a fresh native replay")
        for name in spec["configurations"]:
            for suffix in ("sv", "simulate.log"):
                relative = f"{DIRECTORY}/{name}.{suffix}"
                if (temporary / relative).read_bytes() != project_file(root, relative).read_bytes():
                    raise EvidenceError("CDC saved stimulus or raw trace differs from fresh execution")
    current_files(root, result, inputs)
    current_files(root, result, paths, field="outputs")
    return measured


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    try:
        assessment = run(args.project)
    except (EvidenceError, FileExistsError) as exc:
        parser.exit(1, f"CDC execution failed: {exc}\n")
    print(f"CDC task accepted: goal={assessment['goal']}, engineering_status={assessment['status']}. {LIMITS}")


if __name__ == "__main__":
    main()
