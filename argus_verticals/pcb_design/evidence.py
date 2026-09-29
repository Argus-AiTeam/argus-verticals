"""Verify saved evidence against inputs and a fresh, temporary native replay."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    current_files,
    project_file,
    record,
)

from . import native
from .design import INPUTS_DIR, RESULTS, RESULTS_DIR, validate_plan


def validate_verification(root: Path) -> dict:
    root = root.resolve()
    plan, inputs = validate_plan(root)
    result = record(root, RESULTS)
    if result.get("status") != "complete" or result.get("operation") != "kicad-cli":
        raise EvidenceError("PCB execution has no completed native command record")
    version = native.version()
    if result.get("kicad_version") != version:
        raise EvidenceError("KiCad version differs from the recorded execution")
    expected_inputs = {p: f"{INPUTS_DIR}/{p}" for p in inputs}
    if result.get("inputs") != expected_inputs:
        raise EvidenceError("input copies must include exactly the selected native dependency closure and plan")
    current_files(root, result, inputs)
    output = root / RESULTS_DIR / "native"
    paths = native.output_paths(plan, output)
    outputs = {p.relative_to(root).as_posix(): f"{RESULTS_DIR}/retained/{p.relative_to(output).as_posix()}" for p in paths}
    if result.get("outputs") != outputs:
        raise EvidenceError("retain independent copies of every native report and fabrication file")
    current_files(root, result, list(outputs), field="outputs")
    commands = result.get("commands")
    expected_steps = native.steps(plan, output)
    if not isinstance(commands, list) or len(commands) != len(expected_steps):
        raise EvidenceError("native command records do not match selected operations")
    checks = {c["kind"]: c for c in plan.get("checks", [])}
    measured, reports = {}, {}
    for row, (kind, arguments) in zip(commands, expected_steps):
        if not isinstance(row, dict) or (
            row.get("kind") != kind or row.get("command") != arguments
            or row.get("cwd") != str(root / INPUTS_DIR)
            or row.get("log") != str(output / f"{kind}.log")
            or type(row.get("exit_code")) is not int
        ):
            raise EvidenceError("native command, working directory or log identity disagrees")
        project_file(root, (output / f"{kind}.log").relative_to(root).as_posix())
        if kind in checks:
            counts, normalized = native.report(
                output / f"{kind}.json", kind, plan["design"]["schematic" if kind == "erc" else "board"], version,
            )
            if counts["exclusion"] or counts["error"] > checks[kind]["max_errors"] or counts["warning"] > checks[kind]["max_warnings"]:
                raise EvidenceError(f"{kind}: {counts} violates the original acceptance limits")
            if row["exit_code"] != (5 if any(counts.values()) else 0):
                raise EvidenceError("native exit code and report violation counts disagree")
            reports[kind] = normalized
            measured[kind] = counts
        elif row["exit_code"] != 0:
            raise EvidenceError(f"{kind}: export did not succeed")
    measured.update(native.fabrication_measurements(plan, output))
    # Replay a separate copy: KiCad may write local cache/config files even for checks.
    with tempfile.TemporaryDirectory(prefix="argus-pcb-check-") as directory:
        temporary = Path(directory)
        replay_inputs = temporary / "inputs"
        for relative in inputs:
            destination = replay_inputs / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), destination)
        replay = temporary / "native"
        replay_commands = native.execute(replay_inputs, plan, replay)
        replay_paths = native.output_paths(plan, replay)
        if {p.relative_to(replay) for p in replay_paths} != {p.relative_to(output) for p in paths}:
            raise EvidenceError("native replay produced a different set of output files")
        for original, fresh in zip(commands, replay_commands):
            if original["exit_code"] != fresh["exit_code"]:
                raise EvidenceError("native replay exit code disagrees with saved execution")
        for kind, expected in reports.items():
            _, normalized = native.report(
                replay / f"{kind}.json", kind, plan["design"]["schematic" if kind == "erc" else "board"], version,
            )
            if normalized != expected:
                raise EvidenceError(f"{kind}: saved violations disagree with independent native replay")
        for path in paths:
            if path.suffix in (".gbr", ".drl", ".gbrjob") and native.normalized_export(path) != native.normalized_export(replay / path.relative_to(output)):
                raise EvidenceError(f"{path.name}: exported geometry differs from independent native replay")
        for relative in inputs:
            if (replay_inputs / relative).read_bytes() != project_file(root, relative).read_bytes():
                raise EvidenceError("native replay modified a design input")
    current_files(root, result, inputs)
    return measured
