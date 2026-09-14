# digital_circuit

**Purpose:** Verilog/SystemVerilog RTL, testbenches, formal verification, FPGA/ASIC synthesis, timing, and sign-off.

Staged workflow `specification → rtl → verification → synthesis → delivery`. The `benchmark/` subpackage is a separate vertical (`digital_circuit_benchmark`) that inherits this skill tree.

- `stages.py`: contract, checklists, completion checks (uses `argus_skill.verticals.path_evidence`).
- `evidence.py`: fail-closed evidence checks (interface, preflight, verification sources) also consumed by `chip_design` and `benchmark/`.
- `skills/engineer/` (RTL verification, error-guided repair, spec-guidance registry, benchmark execution), `skills/reviewer/`.

Extras: none. Tests: `tests/skills/test_digital_circuit_vertical.py`, `tests/skills/test_digital_circuit_evidence.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
