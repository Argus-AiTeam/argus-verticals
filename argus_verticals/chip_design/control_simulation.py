"""Finite legal APB transactions, raw sampling and independent comparisons."""
from __future__ import annotations

import random
import re
from collections import defaultdict

from argus_verticals.hardware.shared.evidence import EvidenceError

from .control_model import REGISTERS, expected


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
    checks = defaultdict(lambda: {"comparisons": 0, "mismatches": 0})
    witnesses = []
    for cycle, (frame, observed, wanted) in enumerate(zip(frames, samples, expected(spec, config, frames))):
        for signal, value in wanted.items():
            check = checks[frame["case"]]
            check["comparisons"] += 1
            raw = observed[signal]
            actual = None if "x" in raw or "z" in raw else int(raw, 16 if signal == "read_data" else 2)
            if actual != value:
                check["mismatches"] += 1
                if len(witnesses) < 20:
                    witnesses.append({"cycle": cycle, "case": frame["case"], "signal": signal, "expected": value, "observed": raw, "input": frame})
    return {
        "passed": all(row["mismatches"] == 0 for row in checks.values()),
        "samples": len(samples), "checks": dict(checks), "first_mismatches": witnesses,
        "coverage": {
            "write_strobes": sorted({f["strobes"] for f in frames if f["case"] == "byte_strobes" and f["write"]}),
            "wait_cycles": config["wait_cycles"], "random_seed": config["seed"],
            "cases": sorted(checks),
        },
    }
