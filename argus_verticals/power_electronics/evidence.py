"""Bind original converter conditions to current native files and independent replay."""
from __future__ import annotations

import tempfile
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    current_files,
    record,
)

from . import native
from .model import INPUTS_DIR, PLAN, RESULTS, RESULTS_DIR, validate_plan
from .waveform import measurements


def validate_simulation(root: Path) -> dict:
    root = root.resolve()
    if "robustness" in record(root, PLAN):
        from .robustness import validate_robustness
        return validate_robustness(root)
    plan, models, inputs = validate_plan(root)
    result = record(root, RESULTS)
    if result.get("operation") != "ngspice-converter" or result.get("status") != "complete":
        raise EvidenceError("converter study has no completed native execution record")
    if result.get("ngspice_version") != native.version():
        raise EvidenceError("installed ngspice version differs from the execution record")
    if result.get("inputs") != {p: f"{INPUTS_DIR}/{p}" for p in inputs}:
        raise EvidenceError("input copies must match the plan and selected converter models")
    current_files(root, result, inputs)
    outputs = {
        f"{RESULTS_DIR}/native/{run['id']}/{name}": f"{RESULTS_DIR}/retained/{run['id']}/{name}"
        for run in plan["runs"] for name in native.FILES
    }
    if result.get("outputs") != outputs:
        raise EvidenceError("retain independent copies of all native circuit, waveform and console files")
    current_files(root, result, list(outputs), field="outputs")
    rows = result.get("runs")
    if not isinstance(rows, list) or len(rows) != len(plan["runs"]):
        raise EvidenceError("executed runs do not match the selected studies")
    measured, points = {}, {}
    for run, row in zip(plan["runs"], rows):
        model = models[run["model"]]
        output = root / RESULTS_DIR / "native" / run["id"]
        if not isinstance(row, dict) or row.get("id") != run["id"]:
            raise EvidenceError("run identity or order differs from the plan")
        command = row.get("execution")
        if not isinstance(command, dict) or (
            command.get("command") != list(native.COMMAND) or command.get("cwd") != str(output)
            or command.get("log") != str(output / "ngspice.log")
            or type(command.get("exit_code")) is not int or command["exit_code"] != 0
        ):
            raise EvidenceError("native command identity, location or exit status disagrees")
        plot = native.check_output(output, model, run)
        values = measurements(plot, model, run)
        for check in run["checks"]:
            value = values[check["window"]][check["metric"]]
            if not check["minimum"] <= value <= check["maximum"]:
                raise EvidenceError(f"{run['id']}/{check['id']}: {value:g} {check['unit']} outside original bounds")
        with tempfile.TemporaryDirectory(prefix="argus-power-check-") as directory:
            replay = Path(directory) / "native"
            native.execute(model, run, replay)
            fresh = native.check_output(replay, model, run)
            measurements(fresh, model, run)
            if plot != fresh:
                raise EvidenceError(f"{run['id']}: native waveform differs from independent replay")
        measured[run["id"]], points[run["id"]] = values, len(plot.rows)
    for pair in plan["convergence"]:
        coarse, fine = pair["coarse"], pair["fine"]
        if points[fine] <= points[coarse]:
            raise EvidenceError("finer maximum step did not actually increase native sample count")
        delta = abs(measured[coarse][pair["window"]][pair["metric"]] - measured[fine][pair["window"]][pair["metric"]])
        if delta > pair["max_delta"]:
            raise EvidenceError(f"{coarse}/{fine}: time-step comparison delta {delta:g} exceeds original limit")
    current_files(root, result, inputs)
    current_files(root, result, list(outputs), field="outputs")
    return measured
