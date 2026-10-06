"""Execute and independently replay original-input-bound control studies."""
from __future__ import annotations

import argparse
import json
import shutil
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
from argus_verticals.hardware.shared.native import run_monitored

from . import control_simulation
from .control_model import ASSESSMENT, DIRECTORY, LIMITS, RESULTS, resolve, synthesis

COMMAND_TIMEOUT = 30
EXECUTION_TIMEOUT = 240
OUTPUT_BUDGET = 128 * 1024 * 1024


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def commands(spec: dict) -> list[tuple[str, list[str]]]:
    rows = []
    for name, config in spec["configurations"].items():
        prefix = f"{DIRECTORY}/{name}"
        script = "read_verilog -sv -noautowire " + " ".join(spec["sources"])
        script += (
            f"; chparam -set COUNTER_WIDTH {config['counter_width']} -set WAIT_CYCLES {config['wait_cycles']}"
            f" -set BASE_ADDR 32'd{spec['base_address']} {spec['top']}"
            f"; hierarchy -check -top {spec['top']}; synth -top {spec['top']} -flatten -noabc"
            f"; check -assert; write_json {prefix}.netlist.json; write_verilog -noattr {prefix}.synth.v"
            f"; tee -o {prefix}.stats.json stat -json"
        )
        rows.append((f"{name}.synthesis", ["yosys", "-Q", "-T", "-p", script]))
        for model in ("rtl", "synth"):
            sources = spec["sources"] if model == "rtl" else [f"{prefix}.synth.v"]
            rows.extend([
                (f"{name}.{model}.compile", ["iverilog", "-g2012", "-s", "control_tb", "-o", f"{prefix}.{model}.vvp", *sources, f"{prefix}.{model}.tb.sv"]),
                (f"{name}.{model}.simulate", ["vvp", f"{prefix}.{model}.vvp"]),
            ])
    return rows


def execute(root: Path, spec: dict, result: dict) -> None:
    deadline = time.monotonic() + EXECUTION_TIMEOUT

    def limit(command_deadline: float) -> str:
        if time.monotonic() >= command_deadline:
            return "control native command or study exceeded its allowed seconds"
        if sum(p.stat().st_size for p in (root / DIRECTORY).iterdir() if p.is_file()) > OUTPUT_BUDGET:
            return f"control generated output exceeded {OUTPUT_BUDGET} bytes"
        return ""

    for name, config in spec["configurations"].items():
        frames = control_simulation.stimulus(spec, config)
        for model in ("rtl", "synth"):
            text = control_simulation.testbench(spec, config, frames, synthesized=model == "synth")
            (root / DIRECTORY / f"{name}.{model}.tb.sv").write_text(text, encoding="utf-8")
        if stopped := limit(deadline):
            raise EvidenceError(stopped)
    for step, command in commands(spec):
        log = f"{DIRECTORY}/{step}.log"
        row = {"step": step, "command": command, "exit_code": None, "log": log}
        result["commands"].append(row)
        write(root / RESULTS, result)
        command_deadline = min(deadline, time.monotonic() + COMMAND_TIMEOUT)
        if stopped := limit(command_deadline):
            row["stop_reason"] = stopped
            write(root / RESULTS, result)
            raise EvidenceError(stopped)
        with (root / log).open("w", encoding="utf-8") as stream:
            stream.write("$ " + json.dumps(command) + "\n")
            stream.flush()
            try:
                row["exit_code"], stopped = run_monitored(
                    command, root=root, stream=stream, deadline=command_deadline, limit=limit,
                )
            except OSError as exc:
                raise EvidenceError(f"{step}: native command could not finish: {exc}") from exc
        if stopped:
            row["stop_reason"] = stopped
        write(root / RESULTS, result)
        if stopped or row["exit_code"] != 0:
            raise EvidenceError(f"{step}: {stopped or 'native command exited ' + str(row['exit_code'])}; retained {log}")


def assessment(root: Path, spec: dict) -> dict:
    configurations = {}
    for name, config in spec["configurations"].items():
        prefix = f"{DIRECTORY}/{name}"
        structural = synthesis(spec, name, record(root, f"{prefix}.netlist.json"), record(root, f"{prefix}.stats.json"))
        frames = control_simulation.stimulus(spec, config)
        simulations = {}
        for model in ("rtl", "synth"):
            path = project_file(root, f"{prefix}.{model}.simulate.log")
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise EvidenceError(f"{name}/{model}: cannot read native trace: {exc}") from exc
            simulations[model] = control_simulation.measure(spec, config, frames, text)
        configurations[name] = {"synthesis": structural, "simulations": simulations}
    passed = all(
        row["synthesis"]["passed"] and all(sim["passed"] for sim in row["simulations"].values())
        for row in configurations.values()
    )
    return {
        "goal": spec["goal"], "status": "passed" if passed else "failed",
        "conclusion_valid": True, "task_accepted": passed or spec["goal"] == "diagnose",
        "scope": LIMITS, "configurations": configurations,
    }


def output_paths(spec: dict) -> list[str]:
    paths = [ASSESSMENT]
    for name in spec["configurations"]:
        prefix = f"{DIRECTORY}/{name}"
        paths += [f"{prefix}.{suffix}" for suffix in ("netlist.json", "stats.json", "synth.v")]
        for model in ("rtl", "synth"):
            paths += [f"{prefix}.{model}.{suffix}" for suffix in ("tb.sv", "vvp")]
    return paths + [f"{DIRECTORY}/{step}.log" for step, _ in commands(spec)]


def run(root: Path) -> dict:
    root = root.resolve()
    spec, inputs = resolve(root)
    for tool in ("yosys", "iverilog", "vvp"):
        if shutil.which(tool) is None:
            raise EvidenceError(f"{tool} is required for native control execution")
    destination = root / DIRECTORY
    destination.mkdir(parents=True, exist_ok=False)
    result = {"operation": "yosys-icarus-apb4-control", "status": "running", "inputs": {}, "outputs": {}, "commands": []}
    for relative in inputs:
        snapshot = f"{DIRECTORY}/inputs/{relative}"
        target = root / snapshot
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), target)
        result["inputs"][relative] = snapshot
    write(root / RESULTS, result)
    try:
        if resolve(root)[0] != spec:
            raise EvidenceError("original control specification changed during input capture")
        current_files(root, result, inputs)
        execute(root, spec, result)
        measured = assessment(root, spec)
        write(root / ASSESSMENT, measured)
        for relative in output_paths(spec):
            snapshot = f"{DIRECTORY}/retained/{Path(relative).name}"
            (root / snapshot).parent.mkdir(exist_ok=True)
            shutil.copyfile(project_file(root, relative), root / snapshot)
            result["outputs"][relative] = snapshot
        current_files(root, result, inputs)
        result["status"] = "complete"
        write(root / RESULTS, result)
        if not measured["task_accepted"]:
            raise EvidenceError("control design violates original behavior or generic-cell limits; failing evidence retained")
        return measured
    except EvidenceError as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        write(root / RESULTS, result)
        raise


def validate(root: Path) -> dict:
    root = root.resolve()
    spec, inputs = resolve(root)
    result = record(root, RESULTS)
    if result.get("operation") != "yosys-icarus-apb4-control" or result.get("status") != "complete":
        raise EvidenceError("control requires a complete native execution record")
    if result.get("inputs") != {p: f"{DIRECTORY}/inputs/{p}" for p in inputs}:
        raise EvidenceError("control input copies must match the entire original specification/source list")
    current_files(root, result, inputs)
    rows, wanted = result.get("commands"), commands(spec)
    if not isinstance(rows, list) or len(rows) != len(wanted):
        raise EvidenceError("control commands must cover synthesis and both simulations for every configuration")
    for row, (step, command) in zip(rows, wanted):
        if not isinstance(row, dict) or row.get("step") != step or row.get("command") != command or row.get("log") != f"{DIRECTORY}/{step}.log":
            raise EvidenceError("control command or log differs from the original native flow")
        command_result(root, row)
    paths = output_paths(spec)
    if result.get("outputs") != {p: f"{DIRECTORY}/retained/{Path(p).name}" for p in paths}:
        raise EvidenceError("control must retain every generated model, testbench, executable, trace and assessment")
    current_files(root, result, paths, field="outputs")
    measured = assessment(root, spec)
    if record(root, ASSESSMENT) != measured or not measured["task_accepted"]:
        raise EvidenceError("control assessment differs from original bounds/raw evidence or is not accepted")
    with tempfile.TemporaryDirectory(prefix="argus-control-check-") as directory:
        temporary = Path(directory)
        for relative in inputs:
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), target)
        if run(temporary) != measured:
            raise EvidenceError("control measurements disagree with a fresh native replay")
        for name in spec["configurations"]:
            suffixes = ["netlist.json", "stats.json", "synth.v"]
            suffixes += [f"{model}.{suffix}" for model in ("rtl", "synth") for suffix in ("tb.sv", "simulate.log")]
            for suffix in suffixes:
                relative = f"{DIRECTORY}/{name}.{suffix}"
                if (temporary / relative).read_bytes() != project_file(root, relative).read_bytes():
                    raise EvidenceError(f"{relative}: saved native evidence differs from fresh execution")
    current_files(root, result, inputs)
    current_files(root, result, paths, field="outputs")
    return measured


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    try:
        measured = run(args.project)
    except (EvidenceError, FileExistsError) as exc:
        parser.exit(1, f"Control execution failed: {exc}\n")
    print(f"Control native evidence complete: goal={measured['goal']}, engineering_status={measured['status']}. Final completion also requires the Engineer report and independent review. {LIMITS}")


if __name__ == "__main__":
    main()
