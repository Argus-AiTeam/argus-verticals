"""Generate finite stimuli and independently check native scalar output traces."""
from __future__ import annotations

import re

from argus_verticals.hardware.shared.evidence import EvidenceError

from .cdc_model import interface


def clock_value(tick: int, timing: dict) -> int:
    offset = tick - timing["phase_ticks"] - 1
    return int(offset >= 0 and offset % timing["period_ticks"] < timing["period_ticks"] // 2)


def rising(tick: int, timing: dict) -> bool:
    return clock_value(tick, timing) == 1 and clock_value(tick - 1, timing) == 0


def stimulus(spec: dict, configuration: dict) -> list[dict[str, int]]:
    inputs, _ = interface(spec)
    resets = sorted({r["input"] for r in spec["resets"].values()})
    data = [c["input"] for c in spec["crossings"].values()]
    span = (max(r["stages"] for r in spec["resets"].values()) + max(c["stages"] for c in spec["crossings"].values()) + 4)
    span *= max(c["period_ticks"] for c in configuration.values())
    changes, cursor = {1: dict.fromkeys(resets, 0)}, span

    def change(values: dict) -> None:
        nonlocal cursor
        while any(rising(cursor, timing) for timing in configuration.values()):
            cursor += 1
        changes[cursor] = values
        cursor += span

    for reset in resets:
        change({reset: 1})
    if len(data) > 1:
        for selected in data:
            change({name: int(name == selected) for name in data})
            change(dict.fromkeys(data, 0))
        for selected in data:
            change({name: int(name != selected) for name in data})
        change(dict.fromkeys(data, 0))
    for value in (1, 0, 1):
        change(dict.fromkeys(data, value))
    for reset in resets:
        change({reset: 0})
        change({reset: 1})
    for value in (0, 1, 0):
        change(dict.fromkeys(data, value))
    values = dict.fromkeys(inputs, 0)
    values.update(dict.fromkeys(resets, 1))
    frames = [dict(values)]
    for tick in range(1, cursor + 1):
        values.update(changes.get(tick, {}))
        values.update({clock: clock_value(tick, timing) for clock, timing in configuration.items()})
        frames.append(dict(values))
    return frames


def testbench(spec: dict, frames: list[dict]) -> str:
    inputs, outputs = interface(spec)
    lines = ["`timescale 1ns/1ps", "module cdc_tb;"]
    lines += [f"reg {name};" for name in inputs]
    lines += [f"wire {name};" for name in outputs]
    lines += [f"{spec['top']} dut (" + ", ".join(f".{p}({p})" for p in inputs + outputs) + ");", "initial begin"]
    lines += [f"{name} = 1'b{frames[0][name]};" for name in inputs]
    for tick, frame in enumerate(frames[1:], 1):
        lines.append("#0.999;")
        lines += [f"{name} = 1'b{value};" for name, value in frame.items() if value != frames[tick - 1][name]]
        lines.append('#0.001; $display("SAMPLE ' + str(tick) + " " + " ".join(["%b"] * len(outputs)) + '", ' + ", ".join(outputs) + ");")
    lines += ['$display("END CDC");', "$finish;", "end", "endmodule"]
    return "\n".join(lines) + "\n"


def expected(spec: dict, configuration: dict, frames: list[dict]) -> list[dict[str, int]]:
    reset_state = {c: [0] * r["stages"] for c, r in spec["resets"].items()}
    launch = dict.fromkeys(spec["crossings"], 0)
    capture = {c: [0] * r["stages"] for c, r in spec["crossings"].items()}
    observations = []
    for tick, frame in enumerate(frames[1:], 1):
        previous_resets = {c: stages[-1] for c, stages in reset_state.items()}
        for clock, reset in spec["resets"].items():
            if frame[reset["input"]] == 0:
                reset_state[clock] = [0] * reset["stages"]
            elif rising(tick, configuration[clock]):
                reset_state[clock] = [1, *reset_state[clock][:-1]]
        old_launch = dict(launch)
        for name, crossing in spec["crossings"].items():
            src, dst = crossing["source_clock"], crossing["destination_clock"]
            if not previous_resets[src] or not reset_state[src][-1]:
                launch[name] = 0
            elif rising(tick, configuration[src]):
                launch[name] = frame[crossing["input"]]
            if not previous_resets[dst] or not reset_state[dst][-1]:
                capture[name] = [0] * crossing["stages"]
            elif rising(tick, configuration[dst]):
                capture[name] = [old_launch[name], *capture[name][:-1]]
        observations.append({
            **{r["output"]: reset_state[c][-1] for c, r in spec["resets"].items()},
            **{r["output"]: capture[c][-1] for c, r in spec["crossings"].items()},
        })
    return observations


def measure(spec: dict, configuration: dict, text: str) -> dict:
    frames = stimulus(spec, configuration)
    _, outputs = interface(spec)
    rows = re.findall(r"^SAMPLE ([0-9]+) ([01xz ]+)$", text, re.MULTILINE)
    if len(rows) != len(frames) - 1 or text.splitlines().count("END CDC") != 1 or re.search(r"\b(FATAL|ERROR|FAIL)\b", text):
        raise EvidenceError("CDC simulation did not produce one complete, noncontradictory native trace")
    counters = {name: {"comparisons": 0, "mismatches": 0} for name in spec["requirements"]}
    witnesses, values_seen = [], {name: set() for name in outputs}
    expected_rows = expected(spec, configuration, frames)
    reset_by_output = {r["output"]: r["input"] for r in spec["resets"].values()}
    for tick, ((saved_tick, raw), target) in enumerate(zip(rows, expected_rows), 1):
        values = raw.split()
        if int(saved_tick) != tick or len(values) != len(outputs):
            raise EvidenceError("CDC trace timestamps or scalar output columns differ")
        for output, value in zip(outputs, values):
            kind = "level_latency"
            if output in reset_by_output:
                kind = "reset_assert" if frames[tick][reset_by_output[output]] == 0 else "reset_release"
            counters[kind]["comparisons"] += 1
            values_seen[output].add(target[output])
            if value != str(target[output]):
                counters[kind]["mismatches"] += 1
                if len(witnesses) < 32:
                    witnesses.append({"tick": tick, "output": output, "expected": target[output], "observed": value, "requirement": kind})
    if any(seen != {0, 1} for seen in values_seen.values()) or any(c["comparisons"] == 0 for c in counters.values()):
        raise EvidenceError("CDC schedule did not exercise both levels and all reset/transfer comparisons")
    return {
        "passed": all(c["mismatches"] == 0 for c in counters.values()),
        "ticks": len(frames) - 1, "checks": counters, "first_mismatches": witnesses,
        "expected_levels": {name: sorted(values) for name, values in values_seen.items()},
        "data_patterns": {
            "inputs": [c["input"] for c in spec["crossings"].values()],
            "values": [list(pattern) for pattern in sorted({
                tuple(frame[c["input"]] for c in spec["crossings"].values()) for frame in frames
            })],
        },
    }
