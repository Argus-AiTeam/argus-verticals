"""Execute every declared corner and independently recompute coverage and margins."""
from __future__ import annotations

import json
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

from . import native
from .model import INPUTS_DIR, RESULTS, RESULTS_DIR
from .study import Study, resolve_study
from .waveform import measurements

ASSESSMENT = RESULTS_DIR + "/ASSESSMENT.json"
MAX_STUDY_SECONDS = 600
MAX_STUDY_OUTPUT_BYTES = 512 * 1024 * 1024
SCOPE = "Only the declared nominal point and finite Cartesian samples; no continuous-range, probabilistic or physical guarantee."


def _remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise EvidenceError("operating-envelope study exceeded its total time budget")
    return value


def _outputs(study: Study) -> dict[str, str]:
    return {
        f"{RESULTS_DIR}/native/{run['id']}/{name}": f"{RESULTS_DIR}/retained/{run['id']}/{name}"
        for _, run in study.runs for name in native.FILES
    }


def _describe(study: Study) -> list[dict]:
    return [{
        "id": scenario.id, "coordinates": scenario.coordinates, "model": scenario.model,
        "runs": list(scenario.runs),
    } for scenario in study.scenarios]


def _coverage(study: Study, completed: list[str], measured: list[str]) -> dict:
    expected = [run["id"] for _, run in study.runs]
    return {
        "mode": "full_cartesian_plus_nominal",
        "axes": study.specification["axes"],
        "cartesian_points": study.grid_size,
        "expected_scenarios": len(study.scenarios),
        "expected_runs": expected, "completed_runs": completed, "measured_runs": measured,
        "complete": completed == expected and measured == expected,
    }


def _collect(root: Path, study: Study) -> dict:
    result = record(root, RESULTS)
    if result.get("operation") != "ngspice-converter-corners" or result.get("execution_complete") is not True:
        raise EvidenceError("operating-envelope execution is incomplete; inspect the retained diagnostics")
    if result.get("ngspice_version") != native.version():
        raise EvidenceError("installed ngspice version differs from the study record")
    if (result.get("scenarios") != _describe(study) or result.get("design") != study.choices
            or result.get("goal") != study.specification["goal"]):
        raise EvidenceError("recorded scenarios or design choices differ from the complete declared study")
    if result.get("inputs") != {p: f"{INPUTS_DIR}/{p}" for p in study.inputs}:
        raise EvidenceError("input copies must bind the plan, operating specification and nominal model")
    current_files(root, result, list(study.inputs))
    outputs = _outputs(study)
    if result.get("outputs") != outputs:
        raise EvidenceError("native output copies do not cover every expected corner and resolution")
    current_files(root, result, list(outputs), field="outputs")
    rows = result.get("runs")
    if not isinstance(rows, list) or len(rows) != len(study.runs):
        raise EvidenceError("native execution records omit or repeat required study runs")
    measured, points, failures, runs = {}, {}, [], []
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    total_bytes = 0
    for (scenario, run), row in zip(study.runs, rows):
        _remaining(deadline)
        output = root / RESULTS_DIR / "native" / run["id"]
        if not isinstance(row, dict) or row.get("id") != run["id"]:
            raise EvidenceError("study execution order or identity disagrees")
        command = row.get("execution")
        if not isinstance(command, dict) or (
            command.get("command") != list(native.COMMAND) or command.get("cwd") != str(output)
            or command.get("log") != str(output / "ngspice.log")
            or type(command.get("exit_code")) is not int or command["exit_code"] != 0
        ):
            raise EvidenceError("study native command or exit status disagrees")
        total_bytes += sum((output / name).stat().st_size for name in native.FILES)
        if total_bytes > MAX_STUDY_OUTPUT_BYTES:
            raise EvidenceError("study exceeds its aggregate native output budget")
        plot = native.check_output(output, scenario.model, run)
        with tempfile.TemporaryDirectory(prefix="argus-power-corner-check-") as directory:
            replay = Path(directory) / "native"
            native.execute(scenario.model, run, replay, timeout_seconds=_remaining(deadline))
            fresh = native.check_output(replay, scenario.model, run)
            if plot != fresh:
                raise EvidenceError(f"{run['id']}: native waveform differs from independent replay")
        try:
            values = measurements(plot, scenario.model, run)
        except EvidenceError as exc:
            failures.append({"kind": "invalid_measurement", "scenario": scenario.id, "run": run["id"], "reason": str(exc)})
            runs.append({"id": run["id"], "scenario": scenario.id, "native_points": len(plot.rows), "valid": False, "reason": str(exc)})
            continue
        measured[run["id"]], points[run["id"]] = values, len(plot.rows)
        runs.append({"id": run["id"], "scenario": scenario.id, "native_points": len(plot.rows), "valid": True, "measurements": values})
    summaries = []
    for check in study.specification["checks"]:
        observations = []
        for scenario, run in study.runs:
            if run["id"] not in measured:
                continue
            value = measured[run["id"]][check["window"]][check["metric"]]
            lower, upper = value-check["minimum"], check["maximum"]-value
            within = check["minimum"] <= value <= check["maximum"]
            margins = lower >= check.get("margin_lower", 0) and upper >= check.get("margin_upper", 0)
            observation = {
                "scenario": scenario.id, "run": run["id"], "value": value,
                "lower_headroom": lower, "upper_headroom": upper,
                "within_limits": within, "required_margins_met": margins,
            }
            observations.append(observation)
            if not within or not margins:
                failures.append({
                    "kind": "limit" if not within else "margin", "check": check["id"],
                    "unit": check["unit"], **observation,
                })
        summaries.append({
            "id": check["id"], "requirement": check["requirement"], "window": check["window"],
            "metric": check["metric"], "unit": check["unit"],
            "minimum": check["minimum"], "maximum": check["maximum"],
            "required_lower_margin": check.get("margin_lower", 0),
            "required_upper_margin": check.get("margin_upper", 0),
            "evaluated_runs": len(observations), "expected_runs": len(study.runs),
            "worst_observed_lower": min(observations, key=lambda x: x["lower_headroom"]) if observations else None,
            "worst_observed_upper": min(observations, key=lambda x: x["upper_headroom"]) if observations else None,
            "passed": len(observations) == len(study.runs) and all(o["within_limits"] and o["required_margins_met"] for o in observations),
        })
    comparisons = []
    for scenario in study.scenarios:
        coarse, fine = (run["id"] for run in scenario.runs)
        if coarse not in measured or fine not in measured:
            continue
        increased = points[fine] > points[coarse]
        if not increased:
            failures.append({"kind": "sample_count", "scenario": scenario.id, "reason": "fine resolution did not produce more native samples"})
        for comparison in study.specification["convergence"]:
            window, metric = comparison["window"], comparison["metric"]
            delta = abs(measured[coarse][window][metric] - measured[fine][window][metric])
            passed = increased and delta <= comparison["max_delta"]
            comparisons.append({"scenario": scenario.id, **comparison, "delta": delta, "passed": passed})
            if delta > comparison["max_delta"]:
                failures.append({"kind": "refinement", "scenario": scenario.id, **comparison, "delta": delta})
    coverage = _coverage(study, [row["id"] for row in rows], list(measured))
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    _remaining(deadline)
    conclusion_valid = coverage["complete"] and all(c["passed"] for c in comparisons)
    engineering_passed = conclusion_valid and not failures
    goal = study.specification["goal"]
    return {
        "status": "passed" if coverage["complete"] and not failures else "failed",
        "goal": goal, "conclusion_valid": conclusion_valid,
        "task_accepted": conclusion_valid and (goal == "diagnose" or engineering_passed),
        "scope": SCOPE, "design": study.choices, "coverage": coverage,
        "checks": summaries, "comparisons": comparisons, "runs": runs, "failures": failures,
    }


def _failure(report: dict) -> str:
    examples = [
        f"{f.get('run', f.get('scenario', 'study'))}/{f.get('check', f['kind'])}"
        for f in report["failures"][:5]
    ]
    return f"operating-envelope task not accepted ({len(report['failures'])} observations): {', '.join(examples)}; inspect {ASSESSMENT}"


def inspect_study(root: Path) -> dict:
    """Recompute a passed or failed completed study without changing its files."""
    root = root.resolve()
    study = resolve_study(root)
    result = record(root, RESULTS)
    if result.get("status") not in ("complete", "failed"):
        raise EvidenceError("operating-envelope results are not finalized")
    report = _collect(root, study)
    if record(root, ASSESSMENT) != report:
        raise EvidenceError("saved coverage or numerical margins differ from independently recomputed results")
    if result["status"] != ("complete" if report["task_accepted"] else "failed"):
        raise EvidenceError("recorded study status disagrees with its original requirements")
    return report


def validate_robustness(root: Path) -> dict:
    report = inspect_study(root)
    if not report["task_accepted"]:
        raise EvidenceError(_failure(report))
    return report


def run_robustness(root: Path) -> dict:
    root = root.resolve()
    study = resolve_study(root)
    version = native.version()
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    result = {
        "operation": "ngspice-converter-corners", "status": "running", "execution_complete": False,
        "ngspice_version": version, "goal": study.specification["goal"],
        "design": study.choices, "scenarios": _describe(study),
        "inputs": {p: f"{INPUTS_DIR}/{p}" for p in study.inputs}, "outputs": {}, "runs": [],
    }

    def save():
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n")

    save()
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    total_bytes = 0
    try:
        for source, snapshot in result["inputs"].items():
            (root / snapshot).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, source), root / snapshot)
        for scenario, run in study.runs:
            remaining = _remaining(deadline)
            if total_bytes >= MAX_STUDY_OUTPUT_BYTES:
                raise EvidenceError("operating-envelope study exceeded its aggregate native output budget")
            row = {"id": run["id"]}
            result["runs"].append(row)

            def save_command(command):
                row["execution"] = command
                save()

            output = root / RESULTS_DIR / "native" / run["id"]
            native.execute(scenario.model, run, output, save=save_command, timeout_seconds=remaining,
                           maximum_output_bytes=MAX_STUDY_OUTPUT_BYTES-total_bytes)
            total_bytes += sum((output / name).stat().st_size for name in native.FILES)
            for name in native.FILES:
                source = f"{RESULTS_DIR}/native/{run['id']}/{name}"
                snapshot = f"{RESULTS_DIR}/retained/{run['id']}/{name}"
                (root / snapshot).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(project_file(root, source), root / snapshot)
                result["outputs"][source] = snapshot
            save()
        _remaining(deadline)
        result["execution_complete"] = True
        save()
        report = _collect(root, study)
    except (EvidenceError, OSError) as exc:
        result.update(status="failed", error=str(exc))
        completed = [r["id"] for r in result["runs"] if r.get("execution", {}).get("exit_code") == 0]
        report = {"status": "incomplete", "goal": study.specification["goal"],
                  "conclusion_valid": False, "task_accepted": False, "scope": SCOPE, "design": study.choices,
                  "coverage": _coverage(study, completed, []), "error": str(exc)}
        (root / ASSESSMENT).write_text(json.dumps(report, indent=2) + "\n")
        save()
        raise
    (root / ASSESSMENT).write_text(json.dumps(report, indent=2) + "\n")
    result["status"] = "complete" if report["task_accepted"] else "failed"
    if not report["task_accepted"]:
        result["error"] = _failure(report)
    save()
    if not report["task_accepted"]:
        raise EvidenceError(_failure(report))
    return report
