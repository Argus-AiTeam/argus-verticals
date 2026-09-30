"""Export every declared tolerance case and independently assess sampled RF robustness."""
from __future__ import annotations

import json
import math
import shutil
import time
from fractions import Fraction
from pathlib import Path

import numpy as np

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    current_files,
    project_file,
    record,
)

from .evidence import INPUTS_DIR, RESULTS, RESULTS_DIR
from .networks import build_networks, check_export, measurement, versions, write_network
from .study import Study, model_bytes, rendered_networks, resolve_study

ASSESSMENT = RESULTS_DIR + "/ASSESSMENT.json"
OPERATION = "scikit-rf-component-corners"
MAX_OUTPUT_BYTES = 128 * 1024 * 1024
MAX_STUDY_SECONDS = 180
SCOPE = "Finite Cartesian component samples and sampled-frequency refinement; no continuous-band, continuous-tolerance, yield or physical qualification."


def _cases(study: Study):
    for scenario in study.scenarios:
        for resolution in ("coarse", "fine"):
            yield f"{scenario['id']}_{resolution}", scenario, resolution


def _rows(study: Study) -> list[dict]:
    return [
        {"id": identity, "scenario": scenario["id"], "resolution": resolution, "parameters": scenario["parameters"],
         "model": f"{RESULTS_DIR}/cases/{identity}/MODEL.json",
         "studies": [{"id": item["id"], "network": item["network"],
                      "path": f"{RESULTS_DIR}/cases/{identity}/{item['id']}.ts"} for item in study.specification["studies"]]}
        for identity, scenario, resolution in _cases(study)
    ]


def _outputs(study: Study) -> dict[str, str]:
    return {
        source: f"{RESULTS_DIR}/retained/{row['id']}/{Path(source).name}"
        for row in _rows(study) for source in (row["model"], *(item["path"] for item in row["studies"]))
    }


def _budget(deadline: float, size: int) -> None:
    if time.monotonic() > deadline or size > MAX_OUTPUT_BYTES:
        raise EvidenceError("RF robustness exceeds its 180-second or 128-MiB aggregate budget")


def headroom(value: float, check: dict) -> dict:
    exact = Fraction(str(value))
    lower = exact-Fraction(str(check["minimum"]))
    upper = Fraction(str(check["maximum"]))-exact
    lower_surplus = lower-Fraction(str(check.get("margin_lower", 0)))
    upper_surplus = upper-Fraction(str(check.get("margin_upper", 0)))
    try:
        distances = dict(zip(
            ("lower_headroom", "upper_headroom", "lower_margin_surplus", "upper_margin_surplus"),
            map(float, (lower, upper, lower_surplus, upper_surplus)),
        ))
    except OverflowError as exc:
        raise EvidenceError("RF headroom overflowed; use a meaningful measurement scale") from exc
    if not all(math.isfinite(v) for v in distances.values()):
        raise EvidenceError("RF headroom overflowed; use a meaningful measurement scale")
    return {
        **distances,
        "within_limits": check["minimum"] <= value <= check["maximum"],
        "required_margins_met": lower_surplus >= 0 and upper_surplus >= 0,
    }


def _collect(root: Path, study: Study) -> dict:
    result = record(root, RESULTS)
    if result.get("operation") != OPERATION or result.get("execution_complete") is not True:
        raise EvidenceError("RF tolerance execution is incomplete")
    if result.get("versions") != versions():
        raise EvidenceError("installed RF calculation versions differ from recorded execution")
    if result.get("goal") != study.specification["goal"] or result.get("cases") != _rows(study):
        raise EvidenceError("recorded cases differ from complete original RF tolerance coverage")
    if result.get("inputs") != {path: f"{INPUTS_DIR}/{path}" for path in study.inputs}:
        raise EvidenceError("input copies must cover original plan and RF specification")
    outputs = _outputs(study)
    if result.get("outputs") != outputs:
        raise EvidenceError("retain every generated model and exported case network")
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    deadline = time.monotonic() + MAX_STUDY_SECONDS
    size = 0
    failures, runs, observations, measured = [], [], {}, {}
    for (identity, scenario, resolution), row in zip(_cases(study), result["cases"]):
        _budget(deadline, size)
        definitions = rendered_networks(study, scenario, resolution)
        if project_file(root, row["model"]).read_bytes() != model_bytes(definitions):
            raise EvidenceError(f"{identity}: generated model differs from the original common design and sample")
        networks, _ = build_networks(root, definitions, [item["network"] for item in study.specification["studies"]])
        for item, saved in zip(study.specification["studies"], row["studies"]):
            size += project_file(root, saved["path"]).stat().st_size
            _budget(deadline, size)
            network = check_export(root, saved["path"], networks[item["network"]])
            sigma = float(np.max(np.linalg.svd(network.s, compute_uv=False)[:, 0]))
            reciprocity = float(np.max(np.abs(network.s-network.s.transpose(0, 2, 1))))
            valid = sigma <= 1+1e-9 and reciprocity <= 1e-9
            if not valid:
                failures.append({"kind": "network_physics", "case": identity, "study": item["id"],
                                 "sigma_max": sigma, "reciprocity_error": reciprocity})
            values = {}
            for check in item["checks"]:
                key = (item["id"], check["id"])
                observations.setdefault(key, [])
                try:
                    value, unit, frequency = measurement(network, check)
                    if unit != check["unit"] or not math.isfinite(value):
                        raise EvidenceError("measurement unit or finiteness differs from the original check")
                except EvidenceError as exc:
                    valid = False
                    failures.append({"kind": "invalid_measurement", "case": identity, "study": item["id"],
                                     "check": check["id"], "reason": str(exc)})
                    continue
                observation = {
                    "case": identity, "scenario": scenario["id"], "resolution": resolution,
                    "parameters": scenario["parameters"], "frequency_hz": frequency, "value": value,
                    **headroom(value, check),
                }
                observations[key].append(observation)
                values[check["id"]] = {"value": value, "frequency_hz": frequency}
                if not observation["within_limits"] or not observation["required_margins_met"]:
                    failures.append({"kind": "limit" if not observation["within_limits"] else "margin",
                                     "study": item["id"], "check": check["id"], "unit": unit, **observation})
            measured[(identity, item["id"])] = values
            runs.append({"case": identity, "study": item["id"], "network": item["network"],
                         "frequency_points": len(network.f), "sigma_max": sigma,
                         "reciprocity_error": reciprocity, "valid": valid, "measurements": values})
        size += project_file(root, row["model"]).stat().st_size
    checks, comparisons = [], []
    for item in study.specification["studies"]:
        for check in item["checks"]:
            values = observations[(item["id"], check["id"])]
            expected = 2 * len(study.scenarios)
            checks.append({
                "study": item["id"], "id": check["id"], "requirement": check["requirement"], "unit": check["unit"],
                "minimum": check["minimum"], "maximum": check["maximum"],
                "required_lower_margin": check.get("margin_lower", 0), "required_upper_margin": check.get("margin_upper", 0),
                "expected_cases": expected, "evaluated_cases": len(values),
                "worst_observed_lower": min(values, key=lambda row: row["lower_headroom"]) if values else None,
                "worst_observed_upper": min(values, key=lambda row: row["upper_headroom"]) if values else None,
                "passed": len(values) == expected and all(v["within_limits"] and v["required_margins_met"] for v in values),
            })
            for scenario in study.scenarios:
                pair = [measured[(f"{scenario['id']}_{resolution}", item["id"])] for resolution in ("coarse", "fine")]
                if any(check["id"] not in row for row in pair):
                    continue
                delta = abs(pair[1][check["id"]]["value"] - pair[0][check["id"]]["value"])
                if not math.isfinite(delta):
                    raise EvidenceError("RF refinement difference overflowed")
                comparison = {"scenario": scenario["id"], "study": item["id"], "check": check["id"],
                              "unit": check["unit"], "delta": delta, "max_delta": check["max_delta"],
                              "passed": delta <= check["max_delta"]}
                comparisons.append(comparison)
                if not comparison["passed"]:
                    failures.append({"kind": "refinement", **comparison})
    coverage = {
        "mode": "full_cartesian_plus_nominal", "axes": study.specification["axes"],
        "cartesian_points": study.grid_size, "expected_scenarios": len(study.scenarios),
        "scenarios": list(study.scenarios), "expected_cases": [row["id"] for row in _rows(study)],
        "completed_cases": [row["id"] for row in result["cases"]],
        "complete": all(run["valid"] for run in runs),
    }
    valid = coverage["complete"] and all(row["passed"] for row in comparisons)
    accepted = valid and (study.specification["goal"] == "diagnose" or not failures)
    current_files(root, result, list(study.inputs))
    current_files(root, result, list(outputs), field="outputs")
    _budget(deadline, size)
    return {
        "goal": study.specification["goal"], "status": "passed" if valid and not failures else "failed",
        "conclusion_valid": valid, "task_accepted": accepted, "scope": SCOPE,
        "design": study.choices, "coverage": coverage, "checks": checks,
        "comparisons": comparisons, "runs": runs, "failures": failures,
    }


def inspect_study(root: Path) -> dict:
    root = root.resolve()
    report = _collect(root, resolve_study(root))
    if record(root, ASSESSMENT) != report:
        raise EvidenceError("saved RF assessment differs from independent coverage, measurement or margin calculations")
    if record(root, RESULTS).get("status") != ("complete" if report["task_accepted"] else "failed"):
        raise EvidenceError("execution status differs from the original task goal")
    return report


def validate_robustness(root: Path) -> dict:
    report = inspect_study(root)
    if not report["task_accepted"]:
        raise EvidenceError(f"RF robustness task is not accepted; inspect {ASSESSMENT}")
    return report


def run_robustness(root: Path) -> dict:
    root = root.resolve()
    study = resolve_study(root)
    (root / RESULTS_DIR).mkdir(parents=True, exist_ok=False)
    result = {
        "operation": OPERATION, "versions": versions(), "goal": study.specification["goal"],
        "status": "running", "execution_complete": False, "inputs": {}, "cases": [], "outputs": {},
    }

    def save() -> None:
        (root / RESULTS).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for relative in study.inputs:
            target = f"{INPUTS_DIR}/{relative}"
            (root / target).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), root / target)
            result["inputs"][relative] = target
        save()
        current_files(root, result, list(study.inputs))
        frozen = resolve_study(root / INPUTS_DIR)
        if frozen != study:
            raise EvidenceError("RF inputs changed while copying the original specification")
        deadline, size = time.monotonic()+MAX_STUDY_SECONDS, 0
        outputs = _outputs(frozen)
        for (identity, scenario, resolution), row in zip(_cases(frozen), _rows(frozen)):
            _budget(deadline, size)
            definitions = rendered_networks(frozen, scenario, resolution)
            model = root / row["model"]
            model.parent.mkdir(parents=True, exist_ok=False)
            model.write_bytes(model_bytes(definitions))
            networks, _ = build_networks(root / INPUTS_DIR, definitions, [item["network"] for item in frozen.specification["studies"]])
            for item in row["studies"]:
                write_network(root / item["path"], networks[item["network"]])
            for source in (row["model"], *(item["path"] for item in row["studies"])):
                size += (root / source).stat().st_size
                _budget(deadline, size)
                retained = outputs[source]
                (root / retained).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / source, root / retained)
                result["outputs"][source] = retained
            result["cases"].append(row)
            save()
        result["execution_complete"] = True
        save()
        report = _collect(root, study)
        (root / ASSESSMENT).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        result["status"] = "complete" if report["task_accepted"] else "failed"
        save()
        if not report["task_accepted"]:
            raise EvidenceError(f"RF robustness task failed original limits or numerical validity; inspect {ASSESSMENT}")
        return report
    except (EvidenceError, OSError, ValueError) as exc:
        result.update(status="failed", error=str(exc))
        save()
        raise
