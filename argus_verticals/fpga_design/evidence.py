"""Native nextpnr-iCE40 implementation checks, separate from simulation."""
from __future__ import annotations

import math
import re
from pathlib import Path

from argus_verticals.digital_circuit.verification.evidence import (
    EvidenceError,
    command_result,
    current_files,
    names,
    number,
    project_file,
    record,
    validate_simulation,
)

TARGET = "design/FPGA_TARGET.json"
PCF = "constraints/board.pcf"
NETLIST = "implementation/design.json"
TIMING = "implementation/timing.json"
ASC = "implementation/design.asc"
BITSTREAM = "implementation/design.bin"
IMPLEMENTATION_OUTPUTS = (NETLIST, TIMING, ASC, BITSTREAM)


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
