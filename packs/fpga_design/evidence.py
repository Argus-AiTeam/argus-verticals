"""Standalone FPGA evidence check, adapted from Argus fpga_design, digital_circuit verification and
hardware shared evidence. Read-only: it checks project records and never replays commands or programs
a device. The record formats are in records.md next to this file.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

STAGES = ("requirements", "rtl", "verification", "implementation", "bringup", "delivery")
TARGET = "design/FPGA_TARGET.json"
PCF = "constraints/board.pcf"
NETLIST = "implementation/design.json"
TIMING = "implementation/timing.json"
ASC = "implementation/design.asc"
BITSTREAM = "implementation/design.bin"
IMPLEMENTATION_OUTPUTS = (NETLIST, TIMING, ASC, BITSTREAM)


class EvidenceError(ValueError):
    pass


# Common file, numeric and command-record checks.

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
    message = f"{field}: expected a finite number >= {minimum}"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvidenceError(message)
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise EvidenceError(message) from exc
    if not finite or value < minimum:
        raise EvidenceError(message)
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


# Simulation regression: verification/PLAN.json and verification/RESULTS.json.

def validate_plan(root: Path) -> dict:
    plan = record(root, "verification/PLAN.json")
    for field in ("sources", "testbenches"):
        for relative in names(plan.get(field), field):
            project_file(root, relative)
    if "supporting_files" in plan:
        for relative in names(plan["supporting_files"], "supporting_files"):
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
            raise EvidenceError("cdc: this pack has no CDC/reset adapter checker, so a plan composing it cannot pass")
    return plan


def validate_simulation(root: Path, *, additional_inputs: tuple[str, ...] = ()) -> None:
    plan = validate_plan(root)
    results = record(root, "verification/RESULTS.json")
    current_files(root, results, ["verification/PLAN.json", *plan["sources"], *plan["testbenches"], *plan.get("supporting_files", []), *additional_inputs])
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


# FPGA target, native nextpnr-iCE40 implementation and measured bring-up.

def validate_target(root: Path) -> dict:
    target = record(root, TARGET)
    for key in ("top", "board", "part", "package"):
        if not isinstance(target.get(key), str) or not target[key].strip():
            raise EvidenceError(f"{TARGET}: {key} is required")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target["top"]):
        raise EvidenceError("top: expected a Verilog module identifier")
    if target["part"] not in {"hx1k", "hx8k", "lp8k", "up5k"}:
        raise EvidenceError("implementation currently supports iCE40 hx1k/hx8k/lp8k/up5k only")
    clock = target.get("clock")
    if not isinstance(clock, dict) or not isinstance(clock.get("port"), str) or not clock["port"]:
        raise EvidenceError("clock: declare the single input clock port")
    number(clock.get("frequency_mhz"), "clock.frequency_mhz", minimum=0.001)
    sources = names(target.get("sources"), "sources")
    if any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:v|sv)", source) or ".." in Path(source).parts for source in sources):
        raise EvidenceError("sources: this Yosys flow supports plain relative .v/.sv paths without whitespace")
    pins = target.get("pins")
    if not isinstance(pins, dict) or not pins or clock["port"] not in pins:
        raise EvidenceError("pins: include every top-level bit and the clock port")
    if any(not isinstance(pin, str) or not pin.strip() for pin in pins.values()) or len(set(pins.values())) != len(pins):
        raise EvidenceError("pins: distinct nonempty package pins are required")
    number(target.get("io_voltage_v"), "io_voltage_v", minimum=0.1)
    names(target.get("limitations"), "limitations")
    return target


def flow_commands(target: dict) -> dict[str, list[str]]:
    synthesis = "read_verilog -sv " + " ".join(target["sources"])
    synthesis += f"; synth_ice40 -top {target['top']} -json {NETLIST}"
    return {
        "synthesis": ["yosys", "-p", synthesis],
        "place_route": [
            "nextpnr-ice40", f"--{target['part']}", "--package", target["package"],
            "--json", NETLIST, "--pcf", PCF, "--freq", str(target["clock"]["frequency_mhz"]),
            "--seed", "1", "--asc", ASC, "--report", TIMING,
        ],
        "bitstream": ["icepack", ASC, BITSTREAM],
    }


def implementation_inputs(root: Path, target: dict) -> list[str]:
    verification = record(root, "verification/RESULTS.json")
    return [
        TARGET, PCF, *target["sources"], "verification/PLAN.json", "verification/RESULTS.json",
        *(run["log"] for run in verification["runs"]),
    ]


def validate_verification(root: Path) -> dict:
    target = validate_target(root)
    validate_simulation(root, additional_inputs=(TARGET, *target["sources"]))
    return target


def validate_implementation(root: Path) -> dict:
    target = validate_verification(root)
    build = record(root, "implementation/BUILD.json")
    current_files(root, build, implementation_inputs(root, target))
    current_files(root, build, list(IMPLEMENTATION_OUTPUTS), field="outputs")
    commands = build.get("commands")
    if not isinstance(commands, dict) or set(commands) != set(flow_commands(target)):
        raise EvidenceError("implementation: synthesis, place_route and bitstream commands are required")
    for name, expected in flow_commands(target).items():
        run = commands[name]
        if not isinstance(run, dict) or run.get("command") != expected:
            raise EvidenceError(f"{name}: command must match the declared constrained iCE40 flow")
        command_result(root, run)
    constraints: dict[str, str] = {}
    for line in project_file(root, PCF).read_text().splitlines():
        words = line.split("#", 1)[0].split()
        if not words:
            continue
        if len(words) != 3 or words[0] != "set_io" or words[1] in constraints:
            raise EvidenceError("PCF: expected one unique set_io port pin statement per port")
        constraints[words[1]] = words[2]
    if constraints != target["pins"]:
        raise EvidenceError("PCF: pin assignments differ from the target")
    netlist = record(root, NETLIST)
    modules = netlist.get("modules")
    top = modules.get(target["top"]) if isinstance(modules, dict) else None
    ports = top.get("ports") if isinstance(top, dict) else None
    if not isinstance(ports, dict) or target["clock"]["port"] not in ports:
        raise EvidenceError("netlist: declared top/clock is missing")
    physical_ports = set()
    for name, port in ports.items():
        if not isinstance(port, dict) or not isinstance(port.get("bits"), list) or not port["bits"]:
            raise EvidenceError(f"netlist: invalid port {name}")
        bits = port["bits"]
        if len(bits) == 1:
            physical_ports.add(name)
        else:
            offset = port.get("offset", 0)
            if type(offset) is not int:
                raise EvidenceError(f"netlist: invalid port offset {name}")
            physical_ports.update(f"{name}[{offset + bit}]" for bit in range(len(bits)))
    if physical_ports != set(constraints):
        raise EvidenceError("netlist: PCF must constrain every top-level port bit, and no nonexistent bit")
    clock_port = ports[target["clock"]["port"]]
    if clock_port.get("direction") != "input" or len(clock_port["bits"]) != 1:
        raise EvidenceError("netlist: clock must be a scalar input")
    timing = record(root, TIMING)
    clocks = timing.get("fmax")
    if not isinstance(clocks, dict) or len(clocks) != 1:
        raise EvidenceError("nextpnr: exactly one timed clock is supported; empty/multiclock results cannot pass")
    metrics = next(iter(clocks.values()))
    if not isinstance(metrics, dict):
        raise EvidenceError("nextpnr: invalid clock metrics")
    constraint = number(metrics.get("constraint"), "fmax.constraint", minimum=0.001)
    achieved = number(metrics.get("achieved"), "fmax.achieved", minimum=0.001)
    if not math.isclose(constraint, target["clock"]["frequency_mhz"], rel_tol=1e-6) or achieved < constraint:
        raise EvidenceError("nextpnr: missed frequency or incorrect clock constraint")
    resources = timing.get("utilization")
    if not isinstance(resources, dict) or not resources:
        raise EvidenceError("nextpnr: native utilization is required")
    total_used = 0
    for name, usage in resources.items():
        if not isinstance(usage, dict):
            raise EvidenceError(f"nextpnr: invalid resource {name}")
        used, available = usage.get("used"), usage.get("available")
        if type(used) is not int or type(available) is not int or not 0 <= used <= available:
            raise EvidenceError(f"nextpnr: invalid or exceeded resource {name}")
        total_used += used
    if total_used == 0:
        raise EvidenceError("nextpnr: empty implementation")
    for relative in (ASC, BITSTREAM):
        project_file(root, relative)
    return target


def validate_bringup(root: Path) -> None:
    target = validate_implementation(root)
    results = record(root, "bringup/RESULTS.json")
    current_files(root, results, [TARGET, BITSTREAM, "implementation/BUILD.json"])
    if results.get("board") != target["board"]:
        raise EvidenceError("bringup: board differs from the target")
    for field in ("device_id", "programming_permission", "connection"):
        if not isinstance(results.get(field), str) or not results[field].strip():
            raise EvidenceError(f"bringup: {field} must identify the real device and operator permission")
    checks = target.get("bringup_checks")
    if not isinstance(checks, dict) or not checks:
        raise EvidenceError("bringup_checks: declare expected physical observations before measurement")
    run = results.get("measurement")
    if not isinstance(run, dict):
        raise EvidenceError("bringup: actual measurement command and output are required")
    output = command_result(root, run)
    observed = {}
    for name, value in re.findall(r"^MEASURE ([a-z][a-z0-9_]*) ([^\s]+)$", output, re.MULTILINE):
        if name in observed:
            raise EvidenceError(f"bringup: duplicate measurement {name}")
        try:
            observed[name] = float(value)
        except ValueError as exc:
            raise EvidenceError(f"bringup: invalid measurement {name}") from exc
    if set(observed) != set(checks):
        raise EvidenceError("bringup: missing or unplanned physical observation")
    for name, bounds in checks.items():
        if not isinstance(bounds, dict):
            raise EvidenceError(f"bringup: invalid limits for {name}")
        low = number(bounds.get("minimum"), f"{name}.minimum", minimum=-math.inf)
        high = number(bounds.get("maximum"), f"{name}.maximum", minimum=low)
        value = number(observed[name], name, minimum=low)
        if value > high:
            raise EvidenceError(f"bringup: {name} exceeds maximum")


def check(root: Path, stage: str) -> None:
    if stage == "requirements":
        validate_target(root)
    elif stage == "rtl":
        for relative in validate_target(root)["sources"]:
            project_file(root, relative)
    elif stage == "verification":
        validate_verification(root)
    elif stage == "implementation":
        validate_implementation(root)
    elif stage == "bringup":
        validate_bringup(root)
    else:
        validate_bringup(root)
        project_file(root, "delivery/README.md")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fpga-evidence", description="Check one stage's FPGA records (read-only).")
    parser.add_argument("command", choices=["check"], nargs="?", default="check")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--stage", choices=STAGES, required=True)
    args = parser.parse_args(argv)
    try:
        check(Path(args.project_root).resolve(), args.stage)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"fpga_design evidence valid for {args.stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
