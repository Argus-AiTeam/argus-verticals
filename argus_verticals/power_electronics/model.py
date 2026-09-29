"""Explicit converter models, study windows and immutable engineering conditions."""
from __future__ import annotations

import math
import re
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, names, number, record

PLAN = "power/PLAN.json"
RESULTS_DIR = "power/results"
INPUTS_DIR = RESULTS_DIR + "/inputs"
RESULTS = RESULTS_DIR + "/RESULTS.json"
METRICS = {
    "output_mean_v": "V", "output_min_v": "V", "output_max_v": "V", "output_pp_v": "V",
    "inductor_mean_a": "A", "inductor_min_a": "A", "inductor_max_a": "A",
    "inductor_pp_a": "A", "inductor_rms_a": "A", "capacitor_rms_a": "A",
    "switch_peak_v": "V", "switch_peak_a": "A", "rectifier_reverse_peak_v": "V",
    "input_power_w": "W", "output_power_w": "W", "loss_power_w": "W",
    "storage_rate_w": "W", "energy_relative_error": "1", "cycle_mean_relative_change": "1",
}
MODEL_BOUNDS = {
    "inductance_h": (1e-6, 0.1), "capacitance_f": (1e-7, 0.01),
    "inductor_resistance_ohm": (1e-4, 10), "capacitor_esr_ohm": (1e-4, 10),
    "switch_on_resistance_ohm": (1e-4, 10), "switch_off_resistance_ohm": (1e4, 1e9),
    "diode_saturation_current_a": (1e-15, 1e-3), "diode_emission": (0.8, 3),
    "diode_resistance_ohm": (1e-4, 10), "temperature_c": (-40, 125),
}


def text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{field}: expected nonempty text")
    return value


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value):
        raise EvidenceError("use a lowercase letter followed by at most 31 lowercase letters, digits or underscores")
    return value


def bounded(value: object, field: str, low: float, high: float) -> float:
    result = number(value, field, minimum=low)
    if result > high:
        raise EvidenceError(f"{field}: exceeds supported maximum {high:g}")
    return result


def fields(value: object, allowed: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) - allowed:
        raise EvidenceError(f"{label}: expected an object with only supported fields")
    return value


def validate_specification(root: Path) -> dict:
    plan = record(root, PLAN)
    text(plan.get("objective"), "objective")
    names(plan.get("limitations"), "limitations")
    requirements = plan.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise EvidenceError("requirements: map identifiers to observable requirements")
    for key, value in requirements.items():
        identifier(key)
        text(value, "requirement")
    return plan


def read_model(root: Path, relative: object) -> dict:
    path = text(relative, "model")
    if Path(path).as_posix() != path or path.startswith(RESULTS_DIR + "/"):
        raise EvidenceError("model: use a canonical input path outside results")
    return validate_model_values(record(root, path))


def validate_model_values(value: object) -> dict:
    model = fields(value, {*MODEL_BOUNDS, "topology", "source", "validity", "limitations"}, "model")
    if model.get("topology") not in ("buck", "boost"):
        raise EvidenceError("model topology must be buck or boost")
    text(model.get("source"), "model source")
    text(model.get("validity"), "model validity")
    names(model.get("limitations"), "model limitations")
    for key, limits in MODEL_BOUNDS.items():
        bounded(model.get(key), key, *limits)
    return model


def estimated_points(duration: float, maximum_step: float, frequency: float) -> float:
    return duration / maximum_step + 40 * duration * frequency


def declared_models(plan: dict) -> list[str]:
    models = names(plan.get("models"), "models")
    if len(models) > 8:
        raise EvidenceError("at most eight models are supported")
    return models


def validate_model(root: Path) -> dict:
    plan = validate_specification(root)
    for relative in declared_models(plan):
        read_model(root, relative)
    return plan


def _run(run: dict, model: dict) -> None:
    fields(run, {"id", "model", "input_voltage_v", "duty_cycle", "frequency_hz",
                 "load_resistance_ohm", "load_step", "duration_s", "max_step_s", "windows", "checks"}, "run")
    voltage = bounded(run.get("input_voltage_v"), "input_voltage_v", 1, 48)
    duty = bounded(run.get("duty_cycle"), "duty_cycle", 0.1, 0.8)
    period = 1 / bounded(run.get("frequency_hz"), "frequency_hz", 1e3, 5e5)
    duration = bounded(run.get("duration_s"), "duration_s", 20 * period, min(1, 1000 * period))
    step = bounded(run.get("max_step_s"), "max_step_s", period / 1000, period / 50)
    if estimated_points(duration, step, 1 / period) > 80000:
        raise EvidenceError("requested simulation exceeds the conservative 80000-point estimate")
    load = bounded(run.get("load_resistance_ohm"), "load_resistance_ohm", 0.1, 1e4)
    change = run.get("load_step")
    if "load_step" in run:
        change = fields(change, {"time_s", "transition_s", "resistance_ohm"}, "load_step")
        moment = bounded(change.get("time_s"), "load_step.time_s", 10 * period, duration - 10 * period)
        rise = bounded(change.get("transition_s"), "load_step.transition_s", period / 1000, 10 * period)
        if moment + rise > duration - 5 * period:
            raise EvidenceError("load transition must finish before the final five switching periods")
        load = min(load, bounded(change.get("resistance_ohm"), "load_step.resistance_ohm", 0.1, 1e4))
    nominal = voltage * duty if model["topology"] == "buck" else voltage / (1 - duty)
    if nominal > 48 or nominal**2 / load > 100:
        raise EvidenceError("initial adapter bounds ideal output to 48 V and nominal resistive-load power to 100 W")
    windows = run.get("windows")
    if not isinstance(windows, dict) or not 1 <= len(windows) <= 8:
        raise EvidenceError("windows: declare 1-8 named observation intervals")
    for name, window in windows.items():
        identifier(name)
        fields(window, {"kind", "interval_s"}, "window")
        if window.get("kind") not in ("startup", "steady", "load_step"):
            raise EvidenceError("window kind must be startup, steady or load_step")
        interval = window.get("interval_s")
        if not isinstance(interval, list) or len(interval) != 2:
            raise EvidenceError("interval_s: provide [start, stop] in seconds")
        low = bounded(interval[0], "window start", 0, duration)
        high = bounded(interval[1], "window stop", 0, duration)
        if low == 0 or high - low < 2 * period * (1 - 1e-10):
            raise EvidenceError("windows start after zero and span at least two switching periods")
        if window["kind"] == "startup" and (low > period / 10 or (change and high > change["time_s"])):
            raise EvidenceError("startup interval starts within the first tenth-period and precedes any load change")
        if window["kind"] == "load_step" and (
            change is None or not low <= change["time_s"] < change["time_s"] + change["transition_s"] <= high
        ):
            raise EvidenceError("load_step window must contain the actual whole load transition")
        if window["kind"] == "steady":
            cycles = (high - low) / period
            if cycles < 10 - 1e-8 or not math.isclose(cycles, round(cycles), abs_tol=1e-8, rel_tol=0):
                raise EvidenceError("steady windows contain an integer number of at least ten periods")
            if change and not (high <= change["time_s"] or low >= change["time_s"] + change["transition_s"]):
                raise EvidenceError("steady interval must not intersect the load transition")


def validate_checks(run: dict, requirements: dict) -> set[str]:
    checks = run.get("checks")
    if not isinstance(checks, list) or not 1 <= len(checks) <= 32:
        raise EvidenceError("each run needs 1-32 original numerical checks")
    check_ids, used_windows, covered = [], set(), set()
    for check in checks:
        fields(check, {"id", "requirement", "window", "metric", "unit", "minimum", "maximum"}, "check")
        check_ids.append(identifier(check.get("id")))
        requirement = identifier(check.get("requirement"))
        if requirement not in requirements:
            raise EvidenceError("check references an unknown requirement")
        covered.add(requirement)
        window = identifier(check.get("window"))
        if window not in run["windows"]:
            raise EvidenceError("check references an unknown observation window")
        used_windows.add(window)
        metric = check.get("metric")
        if not isinstance(metric, str) or metric not in METRICS or check.get("unit") != METRICS[metric]:
            raise EvidenceError("check metric or unit is unsupported")
        low = number(check.get("minimum"), "minimum", minimum=-math.inf)
        high = number(check.get("maximum"), "maximum", minimum=-math.inf)
        if low > high:
            raise EvidenceError("minimum exceeds maximum")
    names(check_ids, "check ids")
    if used_windows != set(run["windows"]):
        raise EvidenceError("every observation window needs a numerical check")
    return covered


def validate_plan(root: Path) -> tuple[dict, dict, list[str]]:
    plan = validate_specification(root)
    declared = declared_models(plan)
    runs = plan.get("runs")
    if not isinstance(runs, list) or not 1 <= len(runs) <= 8:
        raise EvidenceError("runs: declare 1-8 native converter studies")
    ids, covered, models = [], set(), {}
    for run in runs:
        if not isinstance(run, dict):
            raise EvidenceError("run must be an object")
        ids.append(identifier(run.get("id")))
        relative = text(run.get("model"), "run.model")
        if relative not in declared:
            raise EvidenceError("run model is not declared")
        if relative not in models:
            models[relative] = read_model(root, relative)
        _run(run, models[relative])
        covered.update(validate_checks(run, plan["requirements"]))
    names(ids, "run ids")
    if covered != set(plan["requirements"]):
        raise EvidenceError("every numerical requirement needs a declared check")
    pairs = plan.get("convergence")
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 32:
        raise EvidenceError("declare 1-32 time-step comparisons")
    by_id = {run["id"]: run for run in runs}
    compared, identities = set(), set()
    for pair in pairs:
        fields(pair, {"coarse", "fine", "window", "metric", "max_delta"}, "convergence")
        coarse_id, fine_id = identifier(pair.get("coarse")), identifier(pair.get("fine"))
        if coarse_id not in by_id or fine_id not in by_id or coarse_id == fine_id:
            raise EvidenceError("comparison must identify two distinct declared runs")
        coarse, fine = by_id[coarse_id], by_id[fine_id]
        ignored = {"id", "max_step_s", "checks"}
        if {k: v for k, v in coarse.items() if k not in ignored} != {k: v for k, v in fine.items() if k not in ignored}:
            raise EvidenceError("time-step comparison must preserve model, sources, load, duration and windows")
        if fine["max_step_s"] > 0.5 * coarse["max_step_s"]:
            raise EvidenceError("fine maximum step must be at most half the coarse maximum step")
        window, metric = identifier(pair.get("window")), pair.get("metric")
        if window not in coarse["windows"] or not isinstance(metric, str) or metric not in METRICS:
            raise EvidenceError("comparison window or metric is unsupported")
        identity = coarse_id, fine_id, window, metric
        if identity in identities:
            raise EvidenceError("duplicate time-step comparison")
        identities.add(identity)
        number(pair.get("max_delta"), "comparison max_delta")
        compared.update((coarse_id, fine_id))
    if compared != set(ids):
        raise EvidenceError("every study must participate in a declared time-step comparison")
    return plan, models, sorted({PLAN, *models})
