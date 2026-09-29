"""Recheck current package inputs, native thermal fields and independent re-execution."""
from __future__ import annotations

import tempfile
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    current_files,
    project_file,
    record,
)

from . import native
from .model import INPUTS_DIR, RESULTS, RESULTS_DIR, validate_plan


def validate_thermal(root: Path) -> dict[str, dict]:
    root = root.resolve()
    plan, models, inputs = validate_plan(root)
    result = record(root, RESULTS)
    if result.get("operation") != "gmsh+calculix" or result.get("status") != "complete":
        raise EvidenceError("package study has no completed native execution record")
    if result.get("versions") != native.versions():
        raise EvidenceError("installed native versions differ from the execution record")
    if result.get("inputs") != {p: f"{INPUTS_DIR}/{p}" for p in inputs}:
        raise EvidenceError("input copies must match the plan and selected package models")
    current_files(root, result, inputs)
    outputs = {
        f"{RESULTS_DIR}/native/{run['id']}/{name}": f"{RESULTS_DIR}/retained/{run['id']}/{name}"
        for run in plan["runs"] for name in native.FILES
    }
    if result.get("outputs") != outputs:
        raise EvidenceError("retain independent copies of all native geometry, mesh, input and solution files")
    current_files(root, result, list(outputs), field="outputs")
    rows = result.get("runs")
    if not isinstance(rows, list) or len(rows) != len(plan["runs"]):
        raise EvidenceError("executed run records do not match selected studies")
    measured, meshes = {}, {}
    for run, row in zip(plan["runs"], rows):
        model = models[run["model"]]
        output = root / RESULTS_DIR / "native" / run["id"]
        if not isinstance(row, dict) or row.get("id") != run["id"]:
            raise EvidenceError("run identity or order differs from the plan")
        commands = row.get("commands")
        if not isinstance(commands, list) or len(commands) != 2:
            raise EvidenceError("each thermal run needs actual mesh and solver commands")
        for command, tool in zip(commands, ("gmsh", "calculix")):
            if not isinstance(command, dict) or (
                command.get("tool") != tool or command.get("command") != native.arguments(tool)
                or command.get("cwd") != str(output) or command.get("log") != str(output / f"{tool}.log")
                or type(command.get("exit_code")) is not int or command["exit_code"] != 0
            ):
                raise EvidenceError("native command identity, location or exit status disagrees")
            project_file(root, f"{RESULTS_DIR}/native/{run['id']}/{tool}.log")
        values, mesh = native.measurements(output, model, run)
        for check in run["checks"]:
            value = values[check["metric"]]
            if not check["minimum"] <= value <= check["maximum"]:
                raise EvidenceError(f"{run['id']}/{check['id']}: {value:g} {check['unit']} outside original bounds")
        measured[run["id"]], meshes[run["id"]] = values, mesh
        with tempfile.TemporaryDirectory(prefix="argus-package-check-") as directory:
            replay = Path(directory) / "native"
            native.execute(model, run, replay)
            native.measurements(replay, model, run)
            for name in native.FILES:
                if native.comparable(output / name) != native.comparable(replay / name):
                    raise EvidenceError(f"{run['id']}/{name}: saved native output differs from independent replay")
    for pair in plan.get("convergence", []):
        coarse, fine, metric = pair["coarse"], pair["fine"], pair["metric"]
        if len(meshes[fine].elements) <= len(meshes[coarse].elements):
            raise EvidenceError("finer study did not actually increase the native element count")
        delta = abs(measured[fine][metric] - measured[coarse][metric])
        if delta > pair["max_delta"]:
            raise EvidenceError(f"{coarse}/{fine}: mesh comparison delta {delta:g} exceeds the original limit")
    current_files(root, result, inputs)
    return measured
