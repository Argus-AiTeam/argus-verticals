"""Original declarations and an independent APB4 timer state model."""
from __future__ import annotations

import re
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, names, project_file, record

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


def expected(spec: dict, config: dict, frames: list[dict]) -> list[dict]:
    width_mask = (1 << config["counter_width"]) - 1
    state = {name: 0 for name in REGISTERS}
    age, rows = 0, []
    for frame in frames:
        if not frame["reset"]:
            state = {name: 0 for name in REGISTERS}
            age = 0
        offset = frame["address"] - spec["base_address"]
        selected = bool(frame["reset"] and frame["select"] and frame["enable"])
        complete = selected and age == config["wait_cycles"]
        error = offset not in REGISTERS.values() or (frame["write"] and offset == REGISTERS["count"])
        row = {"irq_before": int(bool(state["status"] & state["mask"]))}
        if selected:
            row["ready"] = int(complete)
        if complete:
            row["error"] = int(error)
            if not frame["write"]:
                register = next((name for name, address in REGISTERS.items() if address == offset), None)
                row["read_data"] = state[register] if register else 0
        old = state.copy()
        event = bool(frame["reset"] and old["control"] & 1 and old["count"] == 0)
        if frame["reset"] and old["control"] & 1:
            if old["count"]:
                state["count"] -= 1
            elif old["control"] & 2:
                state["count"] = old["reload"]
            else:
                state["control"] &= ~1
        clear = 0
        if complete and frame["write"] and not error:
            data, strobes = frame["data"], frame["strobes"]
            if offset == REGISTERS["control"] and strobes & 1:
                state["control"] = data & 3
                if data & 1:
                    state["count"] = old["reload"]
            elif offset == REGISTERS["reload"]:
                state["reload"] = merge_bytes(old["reload"], data, strobes) & width_mask
            elif offset == REGISTERS["scratch"]:
                state["scratch"] = merge_bytes(old["scratch"], data, strobes)
            elif offset == REGISTERS["mask"] and strobes & 1:
                state["mask"] = data & 1
            elif offset == REGISTERS["status"] and strobes & 1:
                clear = data & 1
        state["status"] = int(bool((old["status"] and not clear) or event))
        age = age + 1 if selected and not complete else 0
        row["irq_after"] = int(bool(state["status"] & state["mask"]))
        rows.append(row)
    return rows


def synthesis(spec: dict, name: str, netlist: dict, statistics: dict) -> dict:
    from collections import Counter

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
