# chip_design

**Purpose:** end-to-end digital ASIC/accelerator design from workload and microarchitecture through RTL, physical implementation, and sign-off.

Proportional workflow with independent review and a `metric` completion gate. Inherits `digital_circuit`'s skill tree (`VERTICAL_SKILL_PARENTS = ("digital_circuit",)`) and reuses `argus_verticals.digital_circuit.evidence.validate_verification_sources`.

- `stages.py`: stage order, checklists, primary deliverables, completion checks.
- `evidence.py`: fail-closed structured evidence checks for each stage.
- `environment_audit.py`: `python -m argus_verticals.chip_design.environment_audit catalog|collect|check` for EDA/PDK/FPGA/runtime readiness.
- `tool_registry.py` + `references/specialized_tool_registry.json`: the curated tool and reusable-IP registry (built on `argus_skill.verticals.kernel_engineering.tool_registry`).
- `references/`: workflow, comparison protocol, tape-out readiness notes.
- `skills/engineer/`, `skills/reviewer/`.

Extras: none. Tests: `tests/skills/test_chip_design_vertical.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
