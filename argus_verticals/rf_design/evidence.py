"""Validate RF study inputs and recompute exported network data and bounded measurements."""
from __future__ import annotations

import math
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    current_files,
    names,
    number,
    record,
)

from .networks import build_networks, check_export, identifier, measure, text

PLAN = "rf/PLAN.json"
RESULTS_DIR = "rf/results"
INPUTS_DIR = RESULTS_DIR + "/inputs"
RESULTS = RESULTS_DIR + "/RESULTS.json"
OPERATION = "argus_verticals.rf_design.run_analysis.run_analysis"
METRICS = ("s_real", "s_imag", "s_magnitude", "s_db", "s_phase_deg", "sigma_max", "reciprocity_error")


def validate_specification(root: Path) -> dict:
    plan = record(root, PLAN)
    text(plan.get("objective"), "objective")
    names(plan.get("limitations"), "limitations")
    requirements = plan.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise EvidenceError("requirements: map identifiers to observable RF requirements")
    for key, value in requirements.items():
        identifier(key)
        text(value, f"requirements.{key}")
    return plan


def validate_model(root: Path) -> dict:
    plan = validate_specification(root)
    if "robustness" in plan:
        from .study import resolve_study

        study = resolve_study(root)
        build_networks(root, study.specification["networks"])
        return plan
    build_networks(root, plan.get("networks"))
    return plan


def validate_plan(root: Path) -> tuple[dict, dict, list[str]]:
    return validate_network_plan(root, validate_specification(root))


def validate_network_plan(root: Path, plan: dict) -> tuple[dict, dict, list[str]]:
    studies = plan.get("studies")
    if not isinstance(studies, list) or not 1 <= len(studies) <= 64:
        raise EvidenceError("studies: declare 1-64 selected network studies")
    if any(not isinstance(study, dict) for study in studies):
        raise EvidenceError("each study must be an object")
    networks, inputs = build_networks(
        root, plan.get("networks"), [identifier(study.get("network")) for study in studies],
    )
    ids, covered = [], set()
    for study in studies:
        if not isinstance(study, dict):
            raise EvidenceError("each study must be an object")
        ids.append(identifier(study.get("id")))
        target = identifier(study.get("network"))
        if target not in networks:
            raise EvidenceError(f"unknown study network: {target}")
        checks = study.get("checks")
        if not isinstance(checks, list) or not 1 <= len(checks) <= 128:
            raise EvidenceError("each study needs 1-128 numerical checks")
        check_ids = []
        for check in checks:
            if not isinstance(check, dict):
                raise EvidenceError("each check must be an object")
            check_ids.append(identifier(check.get("id")))
            requirement = identifier(check.get("requirement"))
            if requirement not in plan["requirements"]:
                raise EvidenceError(f"unknown requirement: {requirement}")
            covered.add(requirement)
            if check.get("metric") not in METRICS:
                raise EvidenceError(f"metric: choose one of {METRICS}")
            if check.get("unit") not in ("1", "dB", "deg"):
                raise EvidenceError("unit: use 1, dB or deg")
            low = number(check.get("minimum"), "minimum", minimum=-math.inf)
            high = number(check.get("maximum"), "maximum", minimum=-math.inf)
            if low > high:
                raise EvidenceError("minimum exceeds maximum")
            statistic = check.get("statistic")
            if statistic not in ("at", "min", "max"):
                raise EvidenceError("statistic: use at, min or max")
            if statistic == "at":
                number(check.get("at_hz"), "at_hz")
            else:
                window = check.get("window_hz")
                if not isinstance(window, list) or len(window) != 2:
                    raise EvidenceError("window_hz: declare [start, stop]")
                if number(window[0], "window start") >= number(window[1], "window stop"):
                    raise EvidenceError("window start must precede stop")
            if check["metric"].startswith("s_"):
                ports = check.get("ports")
                if (
                    not isinstance(ports, list) or len(ports) != 2
                    or any(type(port) is not int or not 1 <= port <= networks[target].nports for port in ports)
                ):
                    raise EvidenceError("ports: [response, incident], one-based, within the selected network")
        names(check_ids, "check ids")
    names(ids, "study ids")
    if covered != set(plan["requirements"]):
        raise EvidenceError("every numerical requirement needs a declared check")
    return plan, networks, sorted({PLAN, *inputs})


def result_path(identity: str) -> str:
    return f"{RESULTS_DIR}/networks/{identity}.ts"


def validate_analysis(root: Path) -> dict:
    if "robustness" in validate_specification(root):
        from .robustness import validate_robustness

        return validate_robustness(root)
    plan, networks, required = validate_plan(root)
    result = record(root, RESULTS)
    if result.get("operation") != OPERATION or result.get("status") != "complete":
        raise EvidenceError("RF calculation has no completed execution record")
    versions = result.get("versions")
    if not isinstance(versions, dict):
        raise EvidenceError("record the actual Python, numpy and scikit-rf versions")
    for key in ("python", "numpy", "scikit-rf"):
        text(versions.get(key), f"versions.{key}")
    expected_inputs = {relative: f"{INPUTS_DIR}/{relative}" for relative in required}
    if result.get("inputs") != expected_inputs:
        raise EvidenceError("input copies must match the plan and all actual Touchstone sources")
    current_files(root, result, required)
    studies = result.get("studies")
    if not isinstance(studies, list) or any(not isinstance(item, dict) for item in studies):
        raise EvidenceError("studies: expected execution records")
    executed_ids = names([item.get("id") for item in studies], "executed study ids")
    requested = {study["id"]: study for study in plan["studies"]}
    if set(executed_ids) != set(requested):
        raise EvidenceError("executed studies must match the requested studies exactly")
    expected_outputs = {
        result_path(identity): f"{RESULTS_DIR}/retained/{identity}.ts"
        for identity in requested
    }
    if result.get("outputs") != expected_outputs:
        raise EvidenceError("retain independent copies of every exported network")
    current_files(root, result, list(expected_outputs), field="outputs")
    measured = {}
    for row in studies:
        study = requested[row["id"]]
        if row.get("network") != study["network"] or row.get("path") != result_path(row["id"]):
            raise EvidenceError("study output does not identify the requested network")
        exported = check_export(root, row["path"], networks[study["network"]])
        values = {}
        for check in study["checks"]:
            value, unit = measure(exported, check)
            if unit != check["unit"]:
                raise EvidenceError(f"{row['id']}/{check['id']}: measured {unit}, not {check['unit']}")
            if not math.isfinite(value) or not check["minimum"] <= value <= check["maximum"]:
                raise EvidenceError(
                    f"{row['id']}/{check['id']}: {value:g} {unit} outside "
                    f"[{check['minimum']:g}, {check['maximum']:g}]"
                )
            values[check["id"]] = value
        measured[row["id"]] = values
    return measured
