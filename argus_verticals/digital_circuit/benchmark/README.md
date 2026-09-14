# digital_circuit_benchmark

**Purpose:** single-stage fixed-harness RTL benchmark: interface, RTL, local verification, pre-score elaboration, and attempt handoff.

Direct workflow with one stage (`execute`) and independent review. Registered as `digital_circuit_benchmark = "argus_verticals.digital_circuit.benchmark.stages"`; it ships no `skills/` of its own and inherits `digital_circuit`'s (`VERTICAL_SKILL_PARENTS = ("digital_circuit",)`).

- `stages.py`: the contract, repair-freshness expectations (`argus.core.repair_freshness`), preflight and external-scoring checks, and a CLI (`python -m argus_verticals.digital_circuit.benchmark.stages`).

Extras: none. Tests: `tests/skills/test_digital_circuit_benchmark_vertical.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
