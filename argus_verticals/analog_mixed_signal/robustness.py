"""Execute full parameter studies and independently assess every sampled result."""
from __future__ import annotations

import json
import math
import re
import shutil
import tempfile
import time
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    current_files,
    project_file,
    record,
)
from argus_verticals.hardware.spice import batch
from argus_verticals.hardware.spice.raw import MAX_RAW_BYTES, measure, read_plot

from .evidence import INPUTS_DIR, RESULTS, RESULTS_DIR
from .study import Case, Study, rendered_inputs, resolve_study

ASSESSMENT = RESULTS_DIR + "/ASSESSMENT.json"
FILES = ("wave.raw", "ngspice.log", "console.log")
MAX_STUDY_SECONDS = 600
MAX_STUDY_OUTPUT_BYTES = 512 * 1024 * 1024
SCOPE = "Finite declared parameter samples and numerical sensitivity checks; no continuous-range, statistical or physical qualification."


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EvidenceError("analog study exceeded its aggregate time budget")
    return remaining


def _command(case: Case) -> list[str]:
    return ["ngspice", "-n", "-b", "-r", "../wave.raw", "-o", "../ngspice.log", case.analysis["netlist"]]


def _files(study: Study) -> tuple[str, ...]:
    return (*FILES, *(f"inputs/{path}" for path in study.model_files))


def _outputs(study: Study) -> dict[str, str]:
    return {
        f"{RESULTS_DIR}/native/{case.id}/{path}": f"{RESULTS_DIR}/retained/{case.id}/{path}"
        for case in study.cases for path in _files(study)
    }


def _describe(study: Study) -> list[dict]:
    return [
        {"id": case.id, "scenario": case.scenario, "analysis": case.analysis["id"],
         "parameters": case.parameters, "resolution": case.resolution,
         "directive": case.directive, "reltol": case.reltol}
        for case in study.cases
    ]


def _execute(root: Path, study: Study, case: Case, output: Path, *, deadline: float,
             remaining_bytes: int = MAX_RAW_BYTES, save=None) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    for relative, content in rendered_inputs(root, study, case).items():
        path = output / "inputs" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return batch.run_batch(
        _command(case), output / "inputs", output, _files(study),
        timeout=min(120, _remaining(deadline)),
        output_budget=min(MAX_RAW_BYTES, remaining_bytes), save=save,
    )


def _plot(root: Path, study: Study, case: Case, output: Path):
    for relative, content in rendered_inputs(root, study, case).items():
        if (output / "inputs" / relative).read_bytes() != content:
            raise EvidenceError(f"{case.id}: generated circuit differs from original inputs and declared sample")
    for name in FILES:
        path = output / name
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_RAW_BYTES:
            raise EvidenceError(f"{case.id}: missing, empty or oversized {name}")
    log = (output / "ngspice.log").read_text() + "\n" + (output / "console.log").read_text()
    if re.search(r"(?im)^\s*(?:fatal|error|warning|doAnalyses:|run simulation\(s\) aborted)", log):
        raise EvidenceError(f"{case.id}: native diagnostic requires investigation")
    plot = read_plot(output / "wave.raw", case.analysis["kind"])
    if re.findall(r"No\. of Data Rows\s*:\s*(\d+)", log) != [str(len(plot.rows))]:
        raise EvidenceError(f"{case.id}: native completion count disagrees with waveform")
    return plot


def _collect(root: Path, study: Study, *, replay: bool) -> dict:
    result = record(root, RESULTS)
    if result.get("operation") != "ngspice-analog-corners" or result.get("execution_complete") is not True:
        raise EvidenceError("analog operating-envelope execution is incomplete")
    if result.get("ngspice_version") != batch.version():
        raise EvidenceError("installed ngspice differs from the execution record")
    if result.get("cases") != _describe(study) or result.get("goal") != study.specification["goal"]:
        raise EvidenceError("recorded cases or goal differ from the full original study")
    if result.get("inputs") != {path: f"{INPUTS_DIR}/{path}" for path in study.inputs}:
        raise EvidenceError("input copies must cover original plan, specification and all model files")
    outputs = _outputs(study)
    if result.get("outputs") != outputs:
        raise EvidenceError("native output copies omit or repeat expected sample evidence")
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    rows = result.get("runs")
    if not isinstance(rows, list) or len(rows) != len(study.cases):
        raise EvidenceError("execution records do not match every expected sample and resolution")
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    measured, points, failures, runs = {}, {}, [], []
    total_bytes = 0
    for case, row in zip(study.cases, rows):
        _remaining(deadline)
        output = root / RESULTS_DIR / "native" / case.id
        execution = row.get("execution") if isinstance(row, dict) else None
        if (not isinstance(row, dict) or row.get("id") != case.id or not isinstance(execution, dict)
                or execution.get("command") != _command(case) or execution.get("cwd") != str(output / "inputs")
                or execution.get("log") != str(output / "ngspice.log")
                or type(execution.get("exit_code")) is not int or execution["exit_code"] != 0):
            raise EvidenceError("native execution identity, path or exit status disagrees")
        total_bytes += sum((output / path).stat().st_size for path in _files(study))
        if total_bytes > MAX_STUDY_OUTPUT_BYTES:
            raise EvidenceError("analog study exceeds its aggregate output budget")
        plot = _plot(root, study, case, output)
        if replay:
            with tempfile.TemporaryDirectory(prefix="argus-analog-replay-") as directory:
                replay_output = Path(directory) / "native"
                _execute(root, study, case, replay_output, deadline=deadline)
                if plot != _plot(root, study, case, replay_output):
                    raise EvidenceError(f"{case.id}: native waveform differs from independent replay")
        values, valid = {}, True
        for check in case.analysis["checks"]:
            try:
                value, unit = measure(plot, check)
                if unit != check["unit"] or not math.isfinite(value):
                    raise EvidenceError("measurement is nonfinite or has the wrong physical unit")
                values[check["id"]] = value
            except EvidenceError as exc:
                valid = False
                failures.append({"kind": "invalid_measurement", "run": case.id, "check": check["id"], "reason": str(exc)})
        points[case.id] = len(plot.rows)
        if valid:
            measured[case.id] = values
        runs.append({"id": case.id, "scenario": case.scenario, "analysis": case.analysis["id"],
                     "resolution": case.resolution, "parameters": case.parameters,
                     "native_points": len(plot.rows), "valid": valid, "measurements": values})
    summaries, comparisons = [], []
    for analysis in study.specification["analyses"]:
        relevant = [case for case in study.cases if case.analysis["id"] == analysis["id"]]
        for check in analysis["checks"]:
            observations = []
            for case in relevant:
                if case.id not in measured:
                    continue
                value = measured[case.id][check["id"]]
                lower, upper = value-check["minimum"], check["maximum"]-value
                if not math.isfinite(lower) or not math.isfinite(upper):
                    raise EvidenceError("numerical headroom overflowed; use a meaningful signal scale")
                within = check["minimum"] <= value <= check["maximum"]
                margins = lower >= check.get("margin_lower", 0) and upper >= check.get("margin_upper", 0)
                observation = {"scenario": case.scenario, "run": case.id, "parameters": case.parameters,
                               "value": value, "lower_headroom": lower, "upper_headroom": upper,
                               "within_limits": within, "required_margins_met": margins}
                observations.append(observation)
                if not within or not margins:
                    failures.append({"kind": "limit" if not within else "margin", "analysis": analysis["id"],
                                     "check": check["id"], "unit": check["unit"], **observation})
            summaries.append({
                "analysis": analysis["id"], "id": check["id"], "requirement": check["requirement"],
                "unit": check["unit"], "minimum": check["minimum"], "maximum": check["maximum"],
                "required_lower_margin": check.get("margin_lower", 0), "required_upper_margin": check.get("margin_upper", 0),
                "expected_runs": len(relevant), "evaluated_runs": len(observations),
                "worst_observed_lower": min(observations, key=lambda row: row["lower_headroom"]) if observations else None,
                "worst_observed_upper": min(observations, key=lambda row: row["upper_headroom"]) if observations else None,
                "passed": len(observations) == len(relevant) and all(row["within_limits"] and row["required_margins_met"] for row in observations),
            })
        for scenario in study.scenarios:
            coarse, fine = (f"{scenario['id']}_{analysis['id']}_{resolution}" for resolution in ("coarse", "fine"))
            if coarse not in measured or fine not in measured:
                continue
            increased = analysis["kind"] == "op" or points[fine] > points[coarse]
            if not increased:
                failures.append({"kind": "sample_count", "scenario": scenario["id"], "analysis": analysis["id"]})
            for check in analysis["checks"]:
                delta = abs(measured[coarse][check["id"]] - measured[fine][check["id"]])
                if not math.isfinite(delta):
                    raise EvidenceError("refinement difference overflowed; use a meaningful signal scale")
                comparison = {"scenario": scenario["id"], "analysis": analysis["id"], "check": check["id"],
                              "unit": check["unit"], "max_delta": check["max_delta"], "delta": delta,
                              "method": "relative_tolerance" if analysis["kind"] == "op" else "grid_and_relative_tolerance",
                              "passed": increased and delta <= check["max_delta"]}
                comparisons.append(comparison)
                if delta > check["max_delta"]:
                    failures.append({"kind": "refinement", **comparison})
    expected = [case.id for case in study.cases]
    coverage = {
        "mode": "full_cartesian_plus_nominal", "axes": study.specification["axes"],
        "cartesian_points": study.grid_size, "expected_scenarios": len(study.scenarios),
        "scenarios": list(study.scenarios), "expected_runs": expected,
        "completed_runs": [row["id"] for row in rows], "measured_runs": list(measured),
        "complete": list(measured) == expected,
    }
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    _remaining(deadline)
    valid = coverage["complete"] and all(comparison["passed"] for comparison in comparisons)
    goal = study.specification["goal"]
    return {
        "status": "passed" if valid and not failures else "failed", "goal": goal,
        "conclusion_valid": valid, "task_accepted": valid and (goal == "diagnose" or not failures),
        "scope": SCOPE, "design": study.choices, "coverage": coverage,
        "checks": summaries, "comparisons": comparisons, "runs": runs, "failures": failures,
    }


def inspect_study(root: Path) -> dict:
    root = root.resolve()
    report = _collect(root, resolve_study(root), replay=True)
    if record(root, ASSESSMENT) != report:
        raise EvidenceError("saved assessment differs from independently recomputed coverage, margins or refinements")
    if record(root, RESULTS).get("status") != ("complete" if report["task_accepted"] else "failed"):
        raise EvidenceError("study status disagrees with its fixed completion goal")
    return report


def validate_robustness(root: Path) -> dict:
    report = inspect_study(root)
    if not report["task_accepted"]:
        raise EvidenceError(f"analog study is not accepted: inspect {ASSESSMENT}")
    return report


def run_robustness(root: Path) -> dict:
    root = root.resolve()
    study = resolve_study(root)
    version = batch.version()
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    result = {"operation": "ngspice-analog-corners", "status": "running", "execution_complete": False,
              "ngspice_version": version, "goal": study.specification["goal"], "cases": _describe(study),
              "inputs": {path: f"{INPUTS_DIR}/{path}" for path in study.inputs}, "outputs": {}, "runs": []}

    def save():
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n")

    save()
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    total_bytes = 0
    try:
        for source, target in result["inputs"].items():
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, source), root / target)
        for case in study.cases:
            if total_bytes >= MAX_STUDY_OUTPUT_BYTES:
                raise EvidenceError("analog study exhausted its aggregate output budget")
            row = {"id": case.id}
            result["runs"].append(row)

            def save_command(execution):
                row["execution"] = execution
                save()

            output = root / RESULTS_DIR / "native" / case.id
            _execute(root, study, case, output, deadline=deadline,
                     remaining_bytes=MAX_STUDY_OUTPUT_BYTES-total_bytes, save=save_command)
            total_bytes += sum((output / path).stat().st_size for path in _files(study))
            for path in _files(study):
                source = f"{RESULTS_DIR}/native/{case.id}/{path}"
                target = f"{RESULTS_DIR}/retained/{case.id}/{path}"
                (root / target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(project_file(root, source), root / target)
                result["outputs"][source] = target
            save()
        _remaining(deadline)
        result["execution_complete"] = True
        save()
        report = _collect(root, study, replay=False)
    except (EvidenceError, OSError, UnicodeError) as exc:
        result.update(status="failed", error=str(exc))
        (root / ASSESSMENT).write_text(json.dumps({
            "status": "incomplete", "goal": study.specification["goal"],
            "conclusion_valid": False, "task_accepted": False, "error": str(exc),
        }, indent=2) + "\n")
        save()
        raise
    (root / ASSESSMENT).write_text(json.dumps(report, indent=2) + "\n")
    result["status"] = "complete" if report["task_accepted"] else "failed"
    save()
    if not report["task_accepted"]:
        raise EvidenceError(f"analog study is not accepted: inspect {ASSESSMENT}")
    return report
