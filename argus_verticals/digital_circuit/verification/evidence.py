"""Check a declared verification matrix against reproducible execution records."""
from __future__ import annotations

import re
from pathlib import Path

from argus_verticals.hardware.shared.evidence import (
    EvidenceError,
    command_result,
    current_files,
    names,
    project_file,
    record,
)
from argus_verticals.hardware.shared.evidence import (
    evidence_check_command as evidence_check_command,
)
from argus_verticals.hardware.shared.evidence import number as number


def verification_evidence_contract() -> str:
    return Path(__file__).with_name("evidence-contract.md").read_text(encoding="utf-8")


def validate_plan(root: Path) -> dict:
    plan = record(root, "verification/PLAN.json")
    for field in ("sources", "testbenches"):
        for relative in names(plan.get(field), field):
            project_file(root, relative)
    names(plan.get("configurations"), "configurations")
    cases = names(plan.get("cases"), "cases")
    if any(not re.fullmatch(r"[a-z][a-z0-9_]*", case) for case in cases):
        raise EvidenceError("cases: use lowercase underscore-separated identifiers")
    requirements = plan.get("requirements")
    if not isinstance(requirements, dict) or not requirements:
        raise EvidenceError("requirements: map each requirement to checked cases")
    covered: set[str] = set()
    for requirement, checks in requirements.items():
        if not requirement.strip():
            raise EvidenceError("requirements: empty requirement")
        linked = names(checks, f"requirements.{requirement}")
        if not set(linked) <= set(cases):
            raise EvidenceError(f"requirements.{requirement}: unknown case")
        covered.update(linked)
    if covered != set(cases):
        raise EvidenceError("requirements: every case needs an explicit requirement")
    if "cdc" in plan:
        if type(plan["cdc"]) is not bool:
            raise EvidenceError("cdc: use an explicit boolean to compose CDC/reset checks")
        if plan["cdc"]:
            from .cdc_model import resolve

            spec, _ = resolve(root)
            if not set(spec["sources"]) <= set(plan["sources"]):
                raise EvidenceError("CDC sources must also belong to the verification source list")
    return plan


def _cdc_inputs(root: Path, plan: dict) -> list[str]:
    if not plan.get("cdc", False):
        return []
    from .cdc import validate
    from .cdc_model import ASSESSMENT, RESULTS, resolve

    _, inputs = resolve(root)
    validate(root, require_pass=True)
    return [*inputs, RESULTS, ASSESSMENT]


def validate_simulation(root: Path, *, additional_inputs: tuple[str, ...] = ()) -> None:
    plan = validate_plan(root)
    results = record(root, "verification/RESULTS.json")
    current_files(root, results, ["verification/PLAN.json", *plan["sources"], *plan["testbenches"], *additional_inputs, *_cdc_inputs(root, plan)])
    runs = results.get("runs")
    if not isinstance(runs, list) or not runs:
        raise EvidenceError("runs: a nonempty executed regression is required")
    configurations = []
    for run in runs:
        if not isinstance(run, dict):
            raise EvidenceError("runs: each entry must be an object")
        configurations.append(run.get("configuration"))
        output = command_result(root, run)
        observed: dict[str, int] = {}
        for case, comparisons in re.findall(r"^CHECK ([a-z][a-z0-9_]*) ([0-9]+)$", output, re.MULTILINE):
            if case in observed:
                raise EvidenceError(f"duplicate comparison record: {case}")
            observed[case] = int(comparisons)
        if set(observed) != set(plan["cases"]) or any(count <= 0 for count in observed.values()):
            raise EvidenceError("simulation: every planned case needs positive comparison counts")
        if not re.search(r"^PASS regression$", output, re.MULTILINE):
            raise EvidenceError("simulation: missing final successful comparison result")
        if re.search(r"\b(?:FATAL|ERROR|FAIL)\b", output):
            raise EvidenceError("simulation: contradictory failure in raw output")
    if sorted(configurations, key=str) != sorted(plan["configurations"]):
        raise EvidenceError("simulation: missing, repeated or unplanned configuration")


def validate_formal(root: Path) -> None:
    plan = validate_plan(root)
    formal = plan.get("formal")
    if not isinstance(formal, dict) or formal.get("mode") not in {"bmc", "prove"}:
        raise EvidenceError("formal: declare bmc or prove and distinguish bounded from inductive results")
    depth = formal.get("depth")
    if type(depth) is not int or depth < 1:
        raise EvidenceError("formal.depth must be a positive integer")
    assertions = names(formal.get("assertions"), "formal.assertions")
    covers = names(formal.get("covers"), "formal.covers")
    assumptions = formal.get("assumptions")
    if not isinstance(assumptions, list) or any(
        not isinstance(row, dict)
        or not all(isinstance(row.get(key), str) and row[key].strip() for key in ("expression", "reason"))
        for row in assumptions
    ):
        raise EvidenceError("formal.assumptions: list every assumption and its reason, or explicitly use []")
    results = record(root, "verification/FORMAL.json")
    current_files(root, results, ["verification/PLAN.json", *plan["sources"], *plan["testbenches"], *_cdc_inputs(root, plan)])
    for key, expected in (("assertions", assertions), ("covers", covers)):
        entries = results.get(key)
        if not isinstance(entries, dict) or set(entries) != set(expected):
            raise EvidenceError(f"formal.{key}: results must match every planned property")
        for name, run in entries.items():
            mode = formal["mode"] if key == "assertions" else "cover"
            if not isinstance(run, dict) or run.get("mode") != mode or type(run.get("depth")) is not int or run["depth"] != depth:
                raise EvidenceError(f"formal.{name}: mode/depth does not match the plan")
            output = command_result(root, run)
            if "DONE (PASS, rc=0)" not in output or "DONE (FAIL" in output or "DONE (ERROR" in output:
                raise EvidenceError(f"formal.{name}: expected successful SymbiYosys output")
            if key == "covers":
                project_file(root, run.get("witness"))
