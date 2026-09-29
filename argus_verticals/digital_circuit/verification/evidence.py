"""Check a declared verification matrix against reproducible execution records."""
from __future__ import annotations

import json
import math
import re
import shlex
import sys
from pathlib import Path


def verification_evidence_contract() -> str:
    return Path(__file__).with_name("evidence-contract.md").read_text(encoding="utf-8")


def evidence_check_command(vertical: str, stage: str) -> str:
    script = (
        "from pathlib import Path; "
        "from argus.verticals._base import load_vertical_contract; "
        f"issues = load_vertical_contract({vertical!r}).completion_issues({stage!r}, Path.cwd()); "
        "print(list(issues)); raise SystemExit(bool(issues))"
    )
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}"


class EvidenceError(ValueError):
    pass


def project_file(root: Path, relative: object) -> Path:
    if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise EvidenceError(f"expected a project-relative file, got {relative!r}")
    try:
        path = (root / relative).resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"{relative}: {exc}") from exc
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size == 0:
        raise EvidenceError(f"{relative}: expected a nonempty file inside the project")
    return path


def record(root: Path, relative: str) -> dict:
    try:
        value = json.loads(project_file(root, relative).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{relative}: cannot read JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{relative}: expected a JSON object")
    return value


def names(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if (
        not isinstance(value, list)
        or (not value and not allow_empty)
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise EvidenceError(f"{field}: expected distinct nonempty strings")
    return value


def number(value: object, field: str, *, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise EvidenceError(f"{field}: expected a finite number >= {minimum}")
    return value


def current_files(root: Path, payload: dict, required: list[str], *, field: str = "inputs") -> None:
    copies = payload.get(field)
    if not isinstance(copies, dict) or not set(required) <= copies.keys():
        raise EvidenceError(f"{field}: snapshots must include every required file")
    for source, snapshot in copies.items():
        source_path, copy_path = project_file(root, source), project_file(root, snapshot)
        if source_path.samefile(copy_path) or source_path.read_bytes() != copy_path.read_bytes():
            raise EvidenceError(f"{field}: missing independent copy or changed file {source}")


def command_result(root: Path, run: dict) -> str:
    command = run.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
        raise EvidenceError("command: expected the actual argument vector")
    if type(run.get("exit_code")) is not int or run["exit_code"] != 0:
        raise EvidenceError("command did not exit successfully")
    try:
        return project_file(root, run.get("log")).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"cannot read command output: {exc}") from exc


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
    return plan


def validate_simulation(root: Path, *, additional_inputs: tuple[str, ...] = ()) -> None:
    plan = validate_plan(root)
    results = record(root, "verification/RESULTS.json")
    current_files(root, results, ["verification/PLAN.json", *plan["sources"], *plan["testbenches"], *additional_inputs])
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
    current_files(root, results, ["verification/PLAN.json", *plan["sources"], *plan["testbenches"]])
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
