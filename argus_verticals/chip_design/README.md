# chip_design

**Purpose:** modular digital ASIC/accelerator architecture and subsystem design,
with scoped studies/implementation and an optional complete delivery workflow.

Independent review and the `metric` completion gate remain. New tasks choose the
smallest matching profile: `architecture`, `rtl`, `verification`, `ppa`,
`prototype`, `benchmark`, or explicit `full`. Legacy no-profile tasks retain all
nine stages. See [workflow boundaries](references/workflow.md) and the
[subsystem knowledge map](skills/engineer/chip-architecture-map.md).

Inherits `digital_circuit`'s detailed circuit skill tree
(`VERTICAL_SKILL_PARENTS = ("digital_circuit",)`) and reuses
`argus_verticals.digital_circuit.evidence.validate_verification_sources`.

- `stages.py`: stage order, checklists, primary deliverables, completion checks.
- `evidence.py`: fail-closed structured evidence checks for each stage.
- `environment_audit.py`: `python -m argus_verticals.chip_design.environment_audit catalog|collect|check` for EDA/PDK/FPGA/runtime readiness.
- `tool_registry.py` + `references/specialized_tool_registry.json`: the curated tool and reusable-IP registry (built on `argus.verticals.kernel_engineering.tool_registry`).
- `references/`: workflow, comparison protocol, tape-out readiness notes.
- `skills/engineer/`, `skills/reviewer/`.

Extras: none. Tests: `tests/skills/test_chip_design_vertical.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).

Version 1.x requires Argus workflow-profile support (`VerticalContract.for_profile`)
and digital_circuit 1.x for the expanded library. Upgrade the framework first.
Old frameworks fail visibly; existing projects are not auto-migrated. These
skills do not install EDA tools, PDKs or proprietary licenses.
