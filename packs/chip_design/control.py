"""Bounded apb4-timer-v1 control study: run the native flow, check it, summarize it.

Standalone; adapted from the Argus chip_design control, control_model, control_simulation,
control_report, run_control_reference and the shared hardware evidence helpers. Needs yosys,
iverilog and vvp on PATH. Run from the project workspace:

  python3 '<this folder>/control.py' run --project-root .        native RTL + synthesized study
  python3 '<this folder>/control.py' summary --project-root .    JSON for CONTROL_REVIEW.md Evidence
  python3 '<this folder>/control.py' reference NEW_DIRECTORY     packaged teaching example
  python3 '<this folder>/evidence.py' verification --workflow-profile control --project-root .
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import TextIO


# ---- shared record helpers ---------------------------------------------------------------------

class EvidenceError(ValueError):
    """Raised when control inputs or evidence are absent, unsafe, or contradictory."""


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


def names(value: object, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise EvidenceError(f"{field}: expected distinct nonempty strings")
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


def run_monitored(
    command: list[str], *, root: Path, stream: TextIO,
    deadline: float, limit: Callable[[float], str],
) -> tuple[int, str]:
    stopped = ""
    with subprocess.Popen(
        command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    ) as process:
        try:
            while process.poll() is None:
                if stopped := limit(deadline):
                    break
                time.sleep(0.05)
        finally:
            finished = process.poll() is not None
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    if finished and not stopped:
                        stopped = "native command left owned child processes running"
                except ProcessLookupError:
                    pass
            elif not finished:
                process.kill()
            exit_code = process.wait()
    return exit_code, stopped or limit(deadline)


# ---- original declarations and the independent APB4 timer state model --------------------------

PLAN = "verification/CONTROL_PLAN.json"
DIRECTORY = "verification/control"
RESULTS = f"{DIRECTORY}/RESULTS.json"
ASSESSMENT = f"{DIRECTORY}/ASSESSMENT.json"
CONTRACT = "apb4-timer-v1"
LIMITS = (
    "Finite single-clock APB4 register/timer/interrupt RTL and synthesized-model comparisons. "
    "Generic Yosys cell counts are not physical area, frequency, power or timing closure. "
    "No CDC, CPU, DMA, memory system, analog, board, physical implementation or silicon claim."
)
REGISTERS = {"control": 0, "reload": 4, "count": 8, "status": 12, "mask": 16, "scratch": 20}
PORTS = {
    "PCLK": ("input", 1), "PRESETn": ("input", 1), "PSEL": ("input", 1),
    "PENABLE": ("input", 1), "PWRITE": ("input", 1), "PADDR": ("input", 32),
    "PWDATA": ("input", 32), "PSTRB": ("input", 4), "PPROT": ("input", 3),
    "PREADY": ("output", 1), "PSLVERR": ("output", 1), "PRDATA": ("output", 32),
    "IRQ": ("output", 1),
}


def integer(value: object, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise EvidenceError(f"{label}: expected an integer from {low} to {high}")
    return value


def keys(value: object, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidenceError(f"{label}: expected exactly {sorted(expected)}")


def identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise EvidenceError(f"expected a plain RTL identifier: {value!r}")
    return value


def resolve(root: Path) -> tuple[dict, list[str]]:
    plan = record(root, PLAN)
    keys(plan, {"specification"}, PLAN)
    relative = plan["specification"]
    path = project_file(root, relative)
    if Path(relative).is_relative_to("verification") or path.stat().st_size > 65536:
        raise EvidenceError("control specification must be an original input outside verification, at most 64 KiB")
    spec = record(root, relative)
    keys(spec, {"contract", "goal", "top", "sources", "base_address", "configurations", "max_generic_cells", "limitations"}, "control specification")
    if spec["contract"] != CONTRACT or spec["goal"] not in ("diagnose", "design"):
        raise EvidenceError("control needs contract apb4-timer-v1 and goal diagnose or design")
    identifier(spec["top"])
    base = integer(spec["base_address"], 0, 0xFFFFFF00, "base_address")
    if base % 256:
        raise EvidenceError("base_address must be 256-byte aligned")
    integer(spec["max_generic_cells"], 1, 20000, "max_generic_cells")
    sources = names(spec["sources"], "sources")
    if len(sources) > 16:
        raise EvidenceError("control accepts at most 16 RTL sources")
    total = 0
    for source in sources:
        if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.(v|sv)", source) or Path(source).is_relative_to("verification"):
            raise EvidenceError("control sources must be plain .v/.sv paths outside verification")
        source_path = project_file(root, source)
        total += source_path.stat().st_size
        if total > 262144:
            raise EvidenceError("control sources exceed 256 KiB")
        try:
            text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise EvidenceError(f"{source}: cannot read RTL: {exc}") from exc
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.DOTALL)
        if set(re.findall(r"`([A-Za-z_]\w*)", text)) - {"timescale", "default_nettype"} or set(re.findall(r"\$([A-Za-z_]\w*)", text)) - {"clog2", "bits"}:
            raise EvidenceError("control RTL cannot use macros, includes, external data or simulation system tasks")
    configs = spec["configurations"]
    if not isinstance(configs, dict) or not 2 <= len(configs) <= 8:
        raise EvidenceError("control requires two to eight explicit parameter/seed configurations")
    seen = set()
    for name, config in configs.items():
        identifier(name)
        keys(config, {"counter_width", "wait_cycles", "seed"}, name)
        width = integer(config["counter_width"], 4, 32, "counter_width")
        wait = integer(config["wait_cycles"], 0, 3, "wait_cycles")
        seed = integer(config["seed"], 1, 2147483647, "seed")
        if (width, wait, seed) in seen:
            raise EvidenceError("control configurations must be distinct")
        seen.add((width, wait, seed))
    names(spec["limitations"], "limitations")
    return spec, [PLAN, relative, *sources]


def merge_bytes(old: int, data: int, strobes: int) -> int:
    mask = sum(0xFF << (8 * lane) for lane in range(4) if strobes & (1 << lane))
    return (old & ~mask) | (data & mask)


REFERENCE_EVENTS = (
    "completed_transfers", "wait_observations", "back_to_back_setups",
    "set_clear_races", "async_active_irq_resets", "reset_aborted_transfers",
    "one_shot_expiries", "periodic_expiries", "zero_reload_expiries",
    "maximum_reload_starts", "masked_pending_observations",
    "read_only_write_errors", "invalid_read_errors", "invalid_write_errors",
    "unselected_accesses",
)


def reference_trace(spec: dict, config: dict, frames: list[dict]) -> tuple[list[dict], dict]:
    width_mask = (1 << config["counter_width"]) - 1
    state = {name: 0 for name in REGISTERS}
    age, rows = 0, []
    counts = dict.fromkeys(REFERENCE_EVENTS, 0)
    witnesses: dict[str, list[int]] = {name: [] for name in REFERENCE_EVENTS}
    strobes: dict[str, dict[str, int]] = {"scratch": {}, "reload": {}}

    def event_at(name: str, cycle: int) -> None:
        counts[name] += 1
        if len(witnesses[name]) < 4:
            witnesses[name].append(cycle)

    for cycle, frame in enumerate(frames):
        if not frame["reset"]:
            if state["status"] & state["mask"]:
                event_at("async_active_irq_resets", cycle)
            if cycle and frames[cycle - 1]["reset"] and frames[cycle - 1]["select"] and not rows[-1].get("ready", 0):
                event_at("reset_aborted_transfers", cycle)
            state = {name: 0 for name in REGISTERS}
            age = 0
        elif not frame["select"] and frame["enable"]:
            event_at("unselected_accesses", cycle)
        elif frame["select"] and not frame["enable"] and rows and rows[-1].get("ready") == 1:
            event_at("back_to_back_setups", cycle)
        offset = frame["address"] - spec["base_address"]
        selected = bool(frame["reset"] and frame["select"] and frame["enable"])
        complete = selected and age == config["wait_cycles"]
        error = offset not in REGISTERS.values() or (frame["write"] and offset == REGISTERS["count"])
        row = {"irq_before": int(bool(state["status"] & state["mask"]))}
        if state["status"] and not state["mask"]:
            event_at("masked_pending_observations", cycle)
        if selected:
            row["ready"] = int(complete)
            if not complete:
                event_at("wait_observations", cycle)
        if complete:
            event_at("completed_transfers", cycle)
            row["error"] = int(error)
            if offset not in REGISTERS.values():
                event_at("invalid_write_errors" if frame["write"] else "invalid_read_errors", cycle)
            elif error:
                event_at("read_only_write_errors", cycle)
            if not frame["write"]:
                register = next((name for name, address in REGISTERS.items() if address == offset), None)
                row["read_data"] = state[register] if register else 0
        old = state.copy()
        event = bool(frame["reset"] and old["control"] & 1 and old["count"] == 0)
        if event:
            event_at("periodic_expiries" if old["control"] & 2 else "one_shot_expiries", cycle)
            if old["reload"] == 0:
                event_at("zero_reload_expiries", cycle)
        if frame["reset"] and old["control"] & 1:
            if old["count"]:
                state["count"] -= 1
            elif old["control"] & 2:
                state["count"] = old["reload"]
            else:
                state["control"] &= ~1
        clear = 0
        if complete and frame["write"] and not error:
            data, strobe = frame["data"], frame["strobes"]
            for register in strobes:
                if offset == REGISTERS[register]:
                    strobes[register].setdefault(str(strobe), cycle)
            if offset == REGISTERS["control"] and strobe & 1:
                state["control"] = data & 3
                if data & 1:
                    state["count"] = old["reload"]
                    if old["reload"] == width_mask:
                        event_at("maximum_reload_starts", cycle)
            elif offset == REGISTERS["reload"]:
                state["reload"] = merge_bytes(old["reload"], data, strobe) & width_mask
            elif offset == REGISTERS["scratch"]:
                state["scratch"] = merge_bytes(old["scratch"], data, strobe)
            elif offset == REGISTERS["mask"] and strobe & 1:
                state["mask"] = data & 1
            elif offset == REGISTERS["status"] and strobe & 1:
                clear = data & 1
        if event and clear:
            event_at("set_clear_races", cycle)
        state["status"] = int(bool((old["status"] and not clear) or event))
        age = age + 1 if selected and not complete else 0
        row["irq_after"] = int(bool(state["status"] & state["mask"]))
        rows.append(row)
    return rows, {
        "reference_event_counts": counts,
        "first_event_cycles": witnesses,
        "completed_write_strobes": {name: sorted(map(int, values)) for name, values in strobes.items()},
        "first_strobe_cycles": strobes,
    }


def require_coverage(config: dict, coverage: dict) -> None:
    counts = coverage["reference_event_counts"]
    missing = [name for name in REFERENCE_EVENTS if name != "wait_observations" and counts[name] <= 0]
    if (counts["wait_observations"] > 0) != bool(config["wait_cycles"]):
        missing.append("wait_observations must match the original zero/nonzero wait configuration")
    for register, values in coverage["completed_write_strobes"].items():
        if values != list(range(16)):
            missing.append(f"{register} completed writes must exercise every strobe mask")
    if missing:
        raise EvidenceError("control stimulus lacks required semantic coverage: " + "; ".join(missing))


def synthesis(spec: dict, name: str, netlist: dict, statistics: dict) -> dict:
    try:
        modules = netlist["modules"]
        top = modules[spec["top"]]
        ports, cells = top["ports"], top["cells"]
        stats = statistics["modules"]["\\" + spec["top"]]
        by_type = dict(sorted(Counter(cell["type"] for cell in cells.values()).items()))
        if stats["num_cells"] != len(cells) or stats["num_cells_by_type"] != by_type:
            raise EvidenceError(f"{name}: native cell statistics disagree with the synthesized netlist")
        failures = []
        if set(modules) != {spec["top"]} or top.get("attributes", {}).get("blackbox", "0").strip("0"):
            failures.append("synthesis must retain one flattened, non-blackbox top")
        if set(ports) != set(PORTS) or any(
            ports[p]["direction"] != direction or len(ports[p]["bits"]) != width
            for p, (direction, width) in PORTS.items()
        ):
            failures.append("synthesized interface differs from the complete APB4 control contract")
        if any("LATCH" in cell for cell in by_type):
            failures.append("latches are outside the synchronous control contract")
        if not cells or len(cells) > spec["max_generic_cells"]:
            failures.append("generic cell count is empty or exceeds the original max_generic_cells")
        return {
            "passed": not failures, "failures": failures,
            "generic_cells": len(cells), "cells_by_type": by_type,
            "max_generic_cells": spec["max_generic_cells"],
            "headroom_cells": spec["max_generic_cells"] - len(cells),
        }
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise EvidenceError(f"{name}: invalid native synthesis evidence: {exc}") from exc


# ---- finite legal APB transactions, raw sampling and independent comparisons -------------------

def stimulus(spec: dict, config: dict) -> list[dict]:
    rng = random.Random(config["seed"])
    frames = []
    base, wait = spec["base_address"], config["wait_cycles"]

    def frame(case: str, **values: int) -> None:
        frames.append({
            "case": case, "reset": 1, "select": 0, "enable": 0, "write": 0,
            "address": 0, "data": 0, "strobes": 0, "protection": 0, **values,
        })

    def idle(case: str, cycles: int) -> None:
        for _ in range(cycles):
            frame(case)

    def transfer(case: str, register: str, *, data: int | None = None, strobes: int = 15, address: int | None = None) -> None:
        values = {
            "select": 1, "write": int(data is not None),
            "address": base + REGISTERS[register] if address is None else address,
            "data": data if data is not None else 0, "strobes": strobes if data is not None else 0,
            "protection": rng.randrange(8),
        }
        frame(case, **values)
        for _ in range(wait + 1):
            frame(case, enable=1, **values)

    def reset(case: str) -> None:
        frame(case, reset=0)
        frame(case, reset=0)
        idle(case, 2)

    reset("reset")
    for register in REGISTERS:
        transfer("reset", register)
    for register in REGISTERS:
        frame("unselected", enable=1, write=1, address=base + REGISTERS[register], data=0xFFFFFFFF, strobes=15)
        transfer("unselected", register)
    for strobe in range(16):
        for register in ("scratch", "reload"):
            transfer("byte_strobes", register, data=rng.getrandbits(32), strobes=strobe)
            transfer("byte_strobes", register)
    for offset in (1, 2, 3, 24, 252, 0x10000):
        address = (base + offset) & 0xFFFFFFFF
        transfer("address_errors", "scratch", data=0xFFFFFFFF, address=address)
        transfer("address_errors", "scratch", address=address)
    transfer("read_only", "count", data=0xFFFFFFFF)
    transfer("read_only", "count", data=0, strobes=0)
    transfer("read_only", "count")
    for register in ("control", "status", "mask"):
        transfer("reserved_bits", register, data=0xFFFFFFFC)
        transfer("reserved_bits", register)
        transfer("reserved_bits", register, data=0xFFFFFFFF, strobes=14)
        transfer("reserved_bits", register)
    transfer("one_shot", "reload", data=3)
    transfer("one_shot", "control", data=1)
    idle("one_shot", 12)
    for register in ("control", "count", "status"):
        transfer("one_shot", register)
    transfer("irq_mask", "mask", data=1)
    transfer("irq_mask", "status")
    transfer("irq_mask", "mask", data=0)
    transfer("irq_mask", "status")
    transfer("irq_mask", "mask", data=1)
    transfer("w1c", "status", data=1, strobes=0)
    transfer("w1c", "status")
    transfer("w1c", "status", data=1)
    transfer("w1c", "status")
    transfer("w1c", "status", data=1)
    transfer("periodic", "reload", data=2)
    transfer("periodic", "control", data=3)
    for _ in range(4):
        transfer("periodic", "count")
        transfer("periodic", "status", data=1)
        idle("periodic", 2)
    transfer("periodic", "control", data=0)
    transfer("set_dominates_clear", "reload", data=0)
    transfer("set_dominates_clear", "control", data=3)
    transfer("set_dominates_clear", "status", data=1)
    transfer("set_dominates_clear", "status")
    transfer("set_dominates_clear", "control", data=0)
    transfer("set_dominates_clear", "status", data=1)
    transfer("set_dominates_clear", "status")
    transfer("counter_boundary", "reload", data=0xFFFFFFFF)
    transfer("counter_boundary", "reload")
    transfer("counter_boundary", "control", data=1)
    transfer("counter_boundary", "count")
    idle("counter_boundary", 6)
    transfer("counter_boundary", "count")
    transfer("counter_boundary", "control", data=0)
    transfer("counter_boundary", "count")
    transfer("reset_abort", "mask", data=1)
    transfer("reset_abort", "reload", data=0)
    transfer("reset_abort", "control", data=3)
    idle("reset_abort", 2)
    # Abort a write in setup (zero wait) or while the first access is waiting.
    frame("reset_abort", select=1, write=1, address=base + REGISTERS["scratch"], data=0xDEADBEEF, strobes=15)
    if wait:
        frame("reset_abort", select=1, enable=1, write=1, address=base + REGISTERS["scratch"], data=0xDEADBEEF, strobes=15)
    frame("reset_abort", reset=0, select=1, enable=1, write=1, address=base + REGISTERS["scratch"], data=0xDEADBEEF, strobes=15)
    reset("reset_abort")
    for register in REGISTERS:
        transfer("reset_abort", register)
    for index in range(64):
        if index == 32:
            reset("random")
        register = rng.choice(list(REGISTERS))
        transfer("random", register, data=rng.getrandbits(32) if rng.randrange(2) else None, strobes=rng.randrange(16))
        if index % 5 == 0:
            idle("random", rng.randrange(1, 5))
    reset("final_reset")
    for register in REGISTERS:
        transfer("final_reset", register)
    return frames


def testbench(spec: dict, config: dict, frames: list[dict], *, synthesized: bool = False) -> str:
    parameters = "" if synthesized else (
        f"#(.COUNTER_WIDTH({config['counter_width']}), .WAIT_CYCLES({config['wait_cycles']}), "
        f".BASE_ADDR(32'd{spec['base_address']}))"
    )
    lines = [
        "`timescale 1ns/1ps", "module control_tb;",
        "reg PCLK=0; always #5 PCLK=~PCLK;",
        "reg PRESETn=0, PSEL=0, PENABLE=0, PWRITE=0;",
        "reg [31:0] PADDR=0, PWDATA=0; reg [3:0] PSTRB=0; reg [2:0] PPROT=0;",
        "wire PREADY, PSLVERR, IRQ; wire [31:0] PRDATA;",
        "reg sampled_ready, sampled_error, sampled_irq; reg [31:0] sampled_data;",
        f"{spec['top']} {parameters} dut (.*);", "initial begin",
    ]
    for index, frame in enumerate(frames):
        lines.extend([
            "@(negedge PCLK);",
            f"PRESETn={frame['reset']}; PSEL={frame['select']}; PENABLE={frame['enable']}; PWRITE={frame['write']};",
            f"PADDR=32'd{frame['address']}; PWDATA=32'd{frame['data']}; PSTRB=4'd{frame['strobes']}; PPROT=3'd{frame['protection']};",
            "#4; sampled_ready=PREADY; sampled_error=PSLVERR; sampled_data=PRDATA; sampled_irq=IRQ;",
            "@(posedge PCLK); #1;",
            f'$display("SAMPLE {index} %b %b %h %b %b", sampled_ready, sampled_error, sampled_data, sampled_irq, IRQ);',
        ])
    lines += ['$display("END CONTROL"); $finish;', "end", "endmodule"]
    return "\n".join(lines) + "\n"


def measure(spec: dict, config: dict, frames: list[dict], trace: str) -> dict:
    samples = []
    ended = False
    for line in trace.splitlines():
        if line.startswith("SAMPLE"):
            match = re.fullmatch(r"SAMPLE ([0-9]+) ([01xz]) ([01xz]) ([0-9a-fxz]{8}) ([01xz]) ([01xz])", line)
            if ended or match is None or int(match[1]) != len(samples):
                raise EvidenceError("control trace has malformed, reordered or extra samples")
            samples.append(dict(zip(("ready", "error", "read_data", "irq_before", "irq_after"), match.groups()[1:])))
        elif line == "END CONTROL":
            if ended:
                raise EvidenceError("control trace has repeated termination")
            ended = True
    if not ended or len(samples) != len(frames):
        raise EvidenceError("control trace is incomplete; this is not a valid negative diagnosis")
    expected_rows, coverage = reference_trace(spec, config, frames)
    require_coverage(config, coverage)
    checks = defaultdict(lambda: {"comparisons": 0, "mismatches": 0})
    witnesses = []
    for cycle, (frame, observed, wanted) in enumerate(zip(frames, samples, expected_rows)):
        for port, value in wanted.items():
            check = checks[frame["case"]]
            check["comparisons"] += 1
            raw = observed[port]
            actual = None if "x" in raw or "z" in raw else int(raw, 16 if port == "read_data" else 2)
            if actual != value:
                check["mismatches"] += 1
                if len(witnesses) < 20:
                    witnesses.append({"cycle": cycle, "case": frame["case"], "signal": port, "expected": value, "observed": raw, "input": frame})
    return {
        "passed": all(row["mismatches"] == 0 for row in checks.values()),
        "samples": len(samples), "checks": dict(checks), "first_mismatches": witnesses,
        "coverage": {
            **coverage,
            "write_strobes": coverage["completed_write_strobes"]["scratch"],
            "wait_cycles": config["wait_cycles"], "random_seed": config["seed"],
            "cases": sorted(checks),
        },
    }


# ---- native execution and read-only replay -----------------------------------------------------

COMMAND_TIMEOUT = 30
EXECUTION_TIMEOUT = 240
OUTPUT_BUDGET = 128 * 1024 * 1024


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def commands(spec: dict) -> list[tuple[str, list[str]]]:
    rows = []
    for name, config in spec["configurations"].items():
        prefix = f"{DIRECTORY}/{name}"
        script = "read_verilog -sv -noautowire " + " ".join(spec["sources"])
        script += (
            f"; chparam -set COUNTER_WIDTH {config['counter_width']} -set WAIT_CYCLES {config['wait_cycles']}"
            f" -set BASE_ADDR 32'd{spec['base_address']} {spec['top']}"
            f"; hierarchy -check -top {spec['top']}; synth -top {spec['top']} -flatten -noabc"
            f"; check -assert; write_json {prefix}.netlist.json; write_verilog -noattr {prefix}.synth.v"
            f"; tee -o {prefix}.stats.json stat -json"
        )
        rows.append((f"{name}.synthesis", ["yosys", "-Q", "-T", "-p", script]))
        for model in ("rtl", "synth"):
            sources = spec["sources"] if model == "rtl" else [f"{prefix}.synth.v"]
            rows.extend([
                (f"{name}.{model}.compile", ["iverilog", "-g2012", "-s", "control_tb", "-o", f"{prefix}.{model}.vvp", *sources, f"{prefix}.{model}.tb.sv"]),
                (f"{name}.{model}.simulate", ["vvp", f"{prefix}.{model}.vvp"]),
            ])
    return rows


def execute(root: Path, spec: dict, result: dict) -> None:
    deadline = time.monotonic() + EXECUTION_TIMEOUT

    def limit(command_deadline: float) -> str:
        if time.monotonic() >= command_deadline:
            return "control native command or study exceeded its allowed seconds"
        if sum(p.stat().st_size for p in (root / DIRECTORY).iterdir() if p.is_file()) > OUTPUT_BUDGET:
            return f"control generated output exceeded {OUTPUT_BUDGET} bytes"
        return ""

    for name, config in spec["configurations"].items():
        frames = stimulus(spec, config)
        for model in ("rtl", "synth"):
            text = testbench(spec, config, frames, synthesized=model == "synth")
            (root / DIRECTORY / f"{name}.{model}.tb.sv").write_text(text, encoding="utf-8")
        if stopped := limit(deadline):
            raise EvidenceError(stopped)
    for step, command in commands(spec):
        log = f"{DIRECTORY}/{step}.log"
        row = {"step": step, "command": command, "exit_code": None, "log": log}
        result["commands"].append(row)
        write(root / RESULTS, result)
        command_deadline = min(deadline, time.monotonic() + COMMAND_TIMEOUT)
        if stopped := limit(command_deadline):
            row["stop_reason"] = stopped
            write(root / RESULTS, result)
            raise EvidenceError(stopped)
        with (root / log).open("w", encoding="utf-8") as stream:
            stream.write("$ " + json.dumps(command) + "\n")
            stream.flush()
            try:
                row["exit_code"], stopped = run_monitored(
                    command, root=root, stream=stream, deadline=command_deadline, limit=limit,
                )
            except OSError as exc:
                raise EvidenceError(f"{step}: native command could not finish: {exc}") from exc
        if stopped:
            row["stop_reason"] = stopped
        write(root / RESULTS, result)
        if stopped or row["exit_code"] != 0:
            raise EvidenceError(f"{step}: {stopped or 'native command exited ' + str(row['exit_code'])}; retained {log}")


def assessment(root: Path, spec: dict) -> dict:
    configurations = {}
    for name, config in spec["configurations"].items():
        prefix = f"{DIRECTORY}/{name}"
        structural = synthesis(spec, name, record(root, f"{prefix}.netlist.json"), record(root, f"{prefix}.stats.json"))
        frames = stimulus(spec, config)
        simulations = {}
        for model in ("rtl", "synth"):
            path = project_file(root, f"{prefix}.{model}.simulate.log")
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise EvidenceError(f"{name}/{model}: cannot read native trace: {exc}") from exc
            simulations[model] = measure(spec, config, frames, text)
        configurations[name] = {"synthesis": structural, "simulations": simulations}
    passed = all(
        row["synthesis"]["passed"] and all(sim["passed"] for sim in row["simulations"].values())
        for row in configurations.values()
    )
    return {
        "goal": spec["goal"], "status": "passed" if passed else "failed",
        "conclusion_valid": True, "task_accepted": passed or spec["goal"] == "diagnose",
        "scope": LIMITS, "configurations": configurations,
    }


def output_paths(spec: dict) -> list[str]:
    paths = [ASSESSMENT]
    for name in spec["configurations"]:
        prefix = f"{DIRECTORY}/{name}"
        paths += [f"{prefix}.{suffix}" for suffix in ("netlist.json", "stats.json", "synth.v")]
        for model in ("rtl", "synth"):
            paths += [f"{prefix}.{model}.{suffix}" for suffix in ("tb.sv", "vvp")]
    return paths + [f"{DIRECTORY}/{step}.log" for step, _ in commands(spec)]


def run(root: Path) -> dict:
    root = root.resolve()
    spec, inputs = resolve(root)
    for tool in ("yosys", "iverilog", "vvp"):
        if shutil.which(tool) is None:
            raise EvidenceError(f"{tool} is required for native control execution")
    destination = root / DIRECTORY
    destination.mkdir(parents=True, exist_ok=False)
    result = {"operation": "yosys-icarus-apb4-control", "status": "running", "inputs": {}, "outputs": {}, "commands": []}
    for relative in inputs:
        snapshot = f"{DIRECTORY}/inputs/{relative}"
        target = root / snapshot
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_file(root, relative), target)
        result["inputs"][relative] = snapshot
    write(root / RESULTS, result)
    try:
        if resolve(root)[0] != spec:
            raise EvidenceError("original control specification changed during input capture")
        current_files(root, result, inputs)
        execute(root, spec, result)
        measured = assessment(root, spec)
        write(root / ASSESSMENT, measured)
        for relative in output_paths(spec):
            snapshot = f"{DIRECTORY}/retained/{Path(relative).name}"
            (root / snapshot).parent.mkdir(exist_ok=True)
            shutil.copyfile(project_file(root, relative), root / snapshot)
            result["outputs"][relative] = snapshot
        current_files(root, result, inputs)
        result["status"] = "complete"
        write(root / RESULTS, result)
        if not measured["task_accepted"]:
            raise EvidenceError("control design violates original behavior or generic-cell limits; failing evidence retained")
        return measured
    except EvidenceError as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        write(root / RESULTS, result)
        raise


def validate(root: Path) -> dict:
    root = root.resolve()
    spec, inputs = resolve(root)
    result = record(root, RESULTS)
    if result.get("operation") != "yosys-icarus-apb4-control" or result.get("status") != "complete":
        raise EvidenceError("control requires a complete native execution record")
    if result.get("inputs") != {p: f"{DIRECTORY}/inputs/{p}" for p in inputs}:
        raise EvidenceError("control input copies must match the entire original specification/source list")
    current_files(root, result, inputs)
    rows, wanted = result.get("commands"), commands(spec)
    if not isinstance(rows, list) or len(rows) != len(wanted):
        raise EvidenceError("control commands must cover synthesis and both simulations for every configuration")
    for row, (step, command) in zip(rows, wanted):
        if not isinstance(row, dict) or row.get("step") != step or row.get("command") != command or row.get("log") != f"{DIRECTORY}/{step}.log":
            raise EvidenceError("control command or log differs from the original native flow")
        command_result(root, row)
    paths = output_paths(spec)
    if result.get("outputs") != {p: f"{DIRECTORY}/retained/{Path(p).name}" for p in paths}:
        raise EvidenceError("control must retain every generated model, testbench, executable, trace and assessment")
    current_files(root, result, paths, field="outputs")
    measured = assessment(root, spec)
    if record(root, ASSESSMENT) != measured or not measured["task_accepted"]:
        raise EvidenceError("control assessment differs from original bounds/raw evidence or is not accepted")
    with tempfile.TemporaryDirectory(prefix="chip-control-check-") as directory:
        temporary = Path(directory)
        for relative in inputs:
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(project_file(root, relative), target)
        if run(temporary) != measured:
            raise EvidenceError("control measurements disagree with a fresh native replay")
        for name in spec["configurations"]:
            suffixes = ["netlist.json", "stats.json", "synth.v"]
            suffixes += [f"{model}.{suffix}" for model in ("rtl", "synth") for suffix in ("tb.sv", "simulate.log")]
            for suffix in suffixes:
                relative = f"{DIRECTORY}/{name}.{suffix}"
                if (temporary / relative).read_bytes() != project_file(root, relative).read_bytes():
                    raise EvidenceError(f"{relative}: saved native evidence differs from fresh execution")
    current_files(root, result, inputs)
    current_files(root, result, paths, field="outputs")
    return measured


# ---- the Engineer's report and final completion ------------------------------------------------

REPORT = "verification/CONTROL_REVIEW.md"
SECTIONS = ("Scope", "Findings and changes", "Evidence", "Limitations")


def summary(root: Path, measured: dict | None = None) -> dict:
    """Return report facts, not an approval or a substitute for native validation."""
    spec, _ = resolve(root)
    if measured is None:
        measured = record(root, ASSESSMENT)
    try:
        configurations = {}
        for name, parameters in spec["configurations"].items():
            row = measured["configurations"][name]
            simulations = {}
            for model, simulation in row["simulations"].items():
                simulations[model] = {
                    "samples": simulation["samples"],
                    "comparisons": sum(c["comparisons"] for c in simulation["checks"].values()),
                    "mismatches": sum(c["mismatches"] for c in simulation["checks"].values()),
                    "reference_event_counts": simulation["coverage"]["reference_event_counts"],
                    "completed_write_strobes": simulation["coverage"]["completed_write_strobes"],
                }
            configurations[name] = {
                "parameters": parameters,
                "generic_cells": row["synthesis"]["generic_cells"],
                "headroom_cells": row["synthesis"]["headroom_cells"],
                "simulations": simulations,
            }
        return {
            "specification": record(root, PLAN)["specification"],
            **{key: spec[key] for key in ("contract", "goal", "top", "sources", "base_address", "max_generic_cells", "limitations")},
            "engineering_status": measured["status"],
            "configurations": configurations,
        }
    except (KeyError, TypeError, AttributeError) as exc:
        raise EvidenceError(f"{REPORT}: cannot summarize incomplete native assessment: {exc}") from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceError(f"{REPORT}: duplicate JSON key {key!r}")
        value[key] = item
    return value


def _read_report(root: Path) -> tuple[bytes, str]:
    path = project_file(root, REPORT)
    if path.stat().st_size > 65536:
        raise EvidenceError(f"{REPORT}: report exceeds 64 KiB")
    try:
        original = path.read_bytes()
        text = original.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"{REPORT}: cannot read report: {exc}") from exc
    sections: dict[str, list[str]] = {}
    current = None
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("## "):
            title = line[3:].strip()
            if title not in SECTIONS or title in sections:
                raise EvidenceError(f"{REPORT}: unexpected or repeated section {title!r}")
            current = title
            sections[title] = []
        elif current is not None:
            sections[current].append(line)
    if fenced or set(sections) != set(SECTIONS):
        raise EvidenceError(f"{REPORT}: requires sections {', '.join(SECTIONS)} and closed code fences")
    for title in ("Scope", "Findings and changes", "Limitations"):
        prose = re.sub(r"(?ms)^```[^\n]*\n.*?^```[ \t]*$", "", "\n".join(sections[title]))
        if not any(line.strip() and not line.lstrip().startswith("#") for line in prose.splitlines()):
            raise EvidenceError(f"{REPORT}: {title} requires Engineer-authored prose")
    evidence = re.fullmatch(r"\s*```json[ \t]*\n(.*?)\n```[ \t]*\s*", "\n".join(sections["Evidence"]), re.DOTALL)
    if evidence is None:
        raise EvidenceError(f"{REPORT}: Evidence must contain exactly one JSON summary block")
    try:
        payload = json.loads(evidence[1], object_pairs_hook=_unique_object)
        canonical = json.dumps(payload, sort_keys=True, allow_nan=False)
    except (json.JSONDecodeError, ValueError) as exc:
        raise EvidenceError(f"{REPORT}: invalid JSON summary: {exc}") from exc
    if not isinstance(payload, dict):
        raise EvidenceError(f"{REPORT}: summary must be a JSON object")
    return original, canonical


def validate_completion(root: Path) -> dict:
    original, report = _read_report(root)
    measured = validate(root)
    if report != json.dumps(summary(root, measured), sort_keys=True, allow_nan=False):
        raise EvidenceError(f"{REPORT}: summary differs from the original specification or independently replayed evidence")
    try:
        if project_file(root, REPORT).read_bytes() != original:
            raise EvidenceError(f"{REPORT}: report changed during final validation")
    except OSError as exc:
        raise EvidenceError(f"{REPORT}: cannot recheck report: {exc}") from exc
    return measured


# ---- packaged teaching example -----------------------------------------------------------------

def prepare_reference(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("rtl", "design", "verification"):
        (root / directory).mkdir()
    shutil.copyfile(Path(__file__).resolve().with_name("control_reference.sv"), root / "rtl/control_reference.sv")
    spec = {
        "contract": "apb4-timer-v1", "goal": "design",
        "top": "control_reference", "sources": ["rtl/control_reference.sv"],
        "base_address": 0x40001000, "max_generic_cells": 2000,
        "configurations": {
            "compact": {"counter_width": 8, "wait_cycles": 0, "seed": 1},
            "waited": {"counter_width": 16, "wait_cycles": 2, "seed": 7},
        },
        "limitations": ["Finite APB4 single-clock control checks and generic synthesis statistics, not physical PPA or a complete SoC."],
    }
    (root / "design/control-spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    (root / "verification/CONTROL_PLAN.json").write_text(json.dumps({"specification": "design/control-spec.json"}) + "\n", encoding="utf-8")


def write_reference_report(root: Path) -> None:
    """Write the example's Engineer report, without claiming independent approval."""
    (root / REPORT).write_text(
        "# Bounded control reference\n\n"
        "## Scope\nThe copied teaching reference uses the original declared APB4 contract and configuration matrix.\n\n"
        "## Findings and changes\nNo RTL repairs were applied to this reference. This generated example report is not independent Reviewer approval.\n\n"
        "## Evidence\n```json\n" + json.dumps(summary(root), indent=2) + "\n```\n\n"
        "## Limitations\n" + LIMITS + "\n",
        encoding="utf-8",
    )


def run_reference(root: Path) -> None:
    prepare_reference(root)
    run(root)
    write_reference_report(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chip-design-control", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands_parser = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "summary"):
        commands_parser.add_parser(name).add_argument("--project-root", type=Path, default=Path("."))
    commands_parser.add_parser("reference").add_argument("output", type=Path, help="new directory; must not exist")
    args = parser.parse_args(argv)
    try:
        if args.command == "summary":
            print(json.dumps(summary(args.project_root.resolve()), indent=2))
            return 0
        if args.command == "reference":
            run_reference(args.output.resolve())
            print(f"PASS: bounded APB4 control RTL, synthesized simulation and generic-cell limits; not physical PPA. Example in {args.output}")
            return 0
        measured = run(args.project_root)
    except (EvidenceError, FileExistsError) as exc:
        print(f"FAIL: control {args.command}: {exc}", file=sys.stderr)
        return 1
    print(f"Control native evidence complete: goal={measured['goal']}, engineering_status={measured['status']}. Final completion also requires the Engineer report and independent review. {LIMITS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
