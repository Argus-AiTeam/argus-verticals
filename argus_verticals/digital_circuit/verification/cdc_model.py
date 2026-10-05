"""Bounded declarations and native structural checks for synchronizer adapters."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from argus_verticals.hardware.shared.evidence import EvidenceError, names, project_file, record

PLAN = "verification/CDC_PLAN.json"
DIRECTORY = "verification/cdc"
RESULTS = f"{DIRECTORY}/RESULTS.json"
ASSESSMENT = f"{DIRECTORY}/ASSESSMENT.json"
LIMITS = (
    "Declared single-bit level adapters and active-low asynchronous-assert/synchronous-release "
    "reset chains only. Finite digital schedules do not model metastability, MTBF, "
    "placement, timing/skew constraints, pulse/bus coherence, asynchronous FIFOs or complete CDC/RDC closure."
)


def _identifier(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", value):
        raise EvidenceError(f"expected a plain RTL identifier: {value!r}")
    return value


def _integer(value: object, low: int, high: int, field: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise EvidenceError(f"{field}: expected an integer from {low} to {high}")
    return value


def _keys(value: object, expected: set[str], field: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise EvidenceError(f"{field}: expected exactly {sorted(expected)}")


def resolve(root: Path) -> tuple[dict, list[str]]:
    plan = record(root, PLAN)
    _keys(plan, {"specification"}, PLAN)
    relative = plan["specification"]
    specification_path = project_file(root, relative)
    if relative == PLAN or Path(relative).is_relative_to(DIRECTORY):
        raise EvidenceError("CDC specification must be an original input outside generated results")
    if specification_path.stat().st_size > 64 * 1024:
        raise EvidenceError("CDC specification exceeds 64 KiB")
    spec = record(root, relative)
    _keys(spec, {"goal", "top", "sources", "clocks", "resets", "crossings", "configurations", "requirements", "limitations"}, "CDC specification")
    if spec["goal"] not in ("diagnose", "design"):
        raise EvidenceError("CDC goal must be diagnose or design")
    _identifier(spec["top"])
    sources = names(spec["sources"], "CDC sources")
    if len(sources) > 16:
        raise EvidenceError("CDC accepts at most 16 source files")
    total = 0
    for source in sources:
        if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_./-]*\.(v|sv)", source) or Path(source).is_relative_to("verification"):
            raise EvidenceError("CDC sources must be plain .v/.sv paths outside verification outputs")
        path = project_file(root, source)
        total += path.stat().st_size
        if total > 256 * 1024:
            raise EvidenceError("CDC source size exceeds 256 KiB")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise EvidenceError(f"{source}: cannot read RTL: {exc}") from exc
        text = re.sub(r"/\*.*?\*/|//[^\n]*", "", text, flags=re.DOTALL)
        directives = re.findall(r"`([a-zA-Z_]\w*)", text)
        calls = re.findall(r"\$([a-zA-Z_]\w*)", text)
        if set(directives) - {"timescale", "default_nettype"} or set(calls) - {"clog2", "bits"}:
            raise EvidenceError("CDC adapter sources cannot use macros, includes, external data or simulation system tasks")
    clocks = names(spec["clocks"], "CDC clocks")
    if not 2 <= len(clocks) <= 4:
        raise EvidenceError("CDC declares two to four independent positive-edge clocks")
    for clock in clocks:
        _identifier(clock)
    _keys(spec["resets"], set(clocks), "CDC resets")
    outputs, reset_inputs = [], set()
    for definition in spec["resets"].values():
        _keys(definition, {"input", "output", "stages"}, "CDC reset")
        reset_inputs.add(_identifier(definition["input"]))
        outputs.append(_identifier(definition["output"]))
        _integer(definition["stages"], 2, 3, "reset stages")
    crossings = spec["crossings"]
    if not isinstance(crossings, dict) or not 1 <= len(crossings) <= 4:
        raise EvidenceError("CDC declares one to four single-bit level crossings")
    data_inputs = []
    for name, crossing in crossings.items():
        _identifier(name)
        _keys(crossing, {"input", "output", "source_clock", "destination_clock", "stages"}, "CDC crossing")
        data_inputs.append(_identifier(crossing["input"]))
        outputs.append(_identifier(crossing["output"]))
        if crossing["source_clock"] not in clocks or crossing["destination_clock"] not in clocks or crossing["source_clock"] == crossing["destination_clock"]:
            raise EvidenceError("CDC crossing requires distinct declared source and destination clocks")
        _integer(crossing["stages"], 2, 3, "crossing stages")
    ports = [*clocks, *sorted(reset_inputs), *data_inputs, *outputs]
    if len(ports) != len(set(ports)):
        raise EvidenceError("CDC clock, reset, data and output ports must be distinct (reset inputs may be shared)")
    configurations = spec["configurations"]
    if not isinstance(configurations, dict) or not 2 <= len(configurations) <= 8:
        raise EvidenceError("CDC needs two to eight explicit clock/phase configurations")
    schedules = []
    for name, configuration in configurations.items():
        _identifier(name)
        _keys(configuration, set(clocks), "CDC configuration clocks")
        for clock, timing in configuration.items():
            _keys(timing, {"period_ticks", "phase_ticks"}, clock)
            period = _integer(timing["period_ticks"], 8, 64, "clock period_ticks")
            if period % 2:
                raise EvidenceError("CDC clock periods must be even integer ticks")
            _integer(timing["phase_ticks"], 0, period - 1, "clock phase_ticks")
        schedules.append(tuple((configuration[c]["period_ticks"], configuration[c]["phase_ticks"]) for c in clocks))
    if len(set(schedules)) != len(schedules):
        raise EvidenceError("CDC configurations must have different periods or phases")
    _keys(spec["requirements"], {"level_latency", "reset_assert", "reset_release"}, "CDC requirements")
    if any(not isinstance(v, str) or not v.strip() for v in spec["requirements"].values()):
        raise EvidenceError("CDC requirements need the original nonempty requirement text")
    names(spec["limitations"], "CDC limitations")
    return spec, [PLAN, relative, *sources]


def interface(spec: dict) -> tuple[list[str], list[str]]:
    inputs = [*spec["clocks"], *sorted({r["input"] for r in spec["resets"].values()}),
              *(c["input"] for c in spec["crossings"].values())]
    outputs = [*(r["output"] for r in spec["resets"].values()), *(c["output"] for c in spec["crossings"].values())]
    return inputs, outputs


def structure(spec: dict, netlist: dict) -> dict:
    try:
        return _structure(spec, netlist)
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise EvidenceError(f"invalid native Yosys cell/connection record: {exc}") from exc


def _structure(spec: dict, netlist: dict) -> dict:
    modules = netlist.get("modules")
    top = modules.get(spec["top"]) if isinstance(modules, dict) else None
    if not isinstance(top, dict) or not isinstance(top.get("ports"), dict) or not isinstance(top.get("cells"), dict):
        raise EvidenceError("Yosys did not produce the declared top and native port/cell records")
    ports, cells = top["ports"], top["cells"]
    inputs, outputs = interface(spec)
    if set(ports) != set(inputs + outputs) or any(
        p.get("direction") != ("input" if name in inputs else "output") or len(p.get("bits", [])) != 1
        for name, p in ports.items()
    ):
        return {"passed": False, "failures": ["top ports differ from the complete declared scalar interface"], "chains": {}}
    bits = {name: p["bits"][0] for name, p in ports.items()}
    if any(type(bits[name]) is not int for name in inputs) or len({bits[name] for name in inputs}) != len(inputs):
        return {"passed": False, "failures": ["declared input ports are aliased or constant in the native model"], "chains": {}}
    drivers, consumers = {}, defaultdict(list)
    atoms, failures, chains, used = set(), [], {}, set()
    for name in outputs:
        consumers[bits[name]].append(("port", name, 0))
    for name, cell in cells.items():
        if cell["type"] not in ("$adff", "$dff"):
            failures.append(f"{name}: unsupported cell {cell['type']} in the declared adapter")
        for port, connections in cell["connections"].items():
            for index, bit in enumerate(connections):
                if cell["port_directions"][port] == "input":
                    consumers[bit].append((name, port, index))
                elif port == "Q" and cell["type"] in ("$adff", "$dff"):
                    drivers[bit] = (name, index)
                    atoms.add((name, index))

    def chain(label: str, output: str, stages: list[tuple[str, str]], first: int | str) -> None:
        bit, route = bits[output], []
        expected_consumer = ("port", output, 0)
        for clock, reset in reversed(stages):
            atom = drivers.get(bit)
            if atom is None or atom in used or atom in {(r["cell"], r["bit"]) for r in route}:
                failures.append(f"{label}: missing, bypassed or shared sequential stage")
                return
            name, index = atom
            cell = cells[name]
            parameters, connections = cell["parameters"], cell["connections"]
            if (cell["type"] != "$adff" or connections["CLK"] != [bits[clock]]
                    or int(parameters["CLK_POLARITY"], 2) != 1
                    or connections.get("ARST") != [bits[reset]]
                    or int(parameters.get("ARST_POLARITY", "1"), 2) != 0
                    or int(parameters.get("ARST_VALUE", "1"), 2) != 0):
                failures.append(f"{label}: stage must use its declared positive-edge clock and active-low zero reset")
                return
            if consumers[bit] != [expected_consumer] and not (
                label.startswith("reset.") and not route
                and all(c == expected_consumer or (c[0] in cells and c[1] == "ARST"
                        and cells[c[0]]["connections"].get("CLK") == [bits[clock]]) for c in consumers[bit])
            ):
                failures.append(f"{label}: intermediate-stage fanout, reconvergence or unexpected output use")
                return
            route.append({"cell": name, "bit": index})
            expected_consumer = (name, "D", index)
            bit = connections["D"][index]
        if bit != first:
            failures.append(f"{label}: chain does not start at its declared input (or reset release constant)")
            return
        chains[label] = list(reversed(route))

    # Keep each bit exclusive, including vector registers expanded into native bit positions.
    for clock, reset in spec["resets"].items():
        label = f"reset.{clock}"
        chain(label, reset["output"], [(clock, reset["input"])] * reset["stages"], "1")
        used.update((r["cell"], r["bit"]) for r in chains.get(label, []))
    for name, crossing in spec["crossings"].items():
        src, dst = crossing["source_clock"], crossing["destination_clock"]
        stages = [(src, spec["resets"][src]["output"])]
        stages += [(dst, spec["resets"][dst]["output"])] * crossing["stages"]
        label = f"crossing.{name}"
        chain(label, crossing["output"], stages, bits[crossing["input"]])
        used.update((r["cell"], r["bit"]) for r in chains.get(label, []))
    if atoms != used:
        failures.append("sequential state is undeclared or did not match an accepted chain")
    return {"passed": not failures, "failures": failures, "chains": chains}
