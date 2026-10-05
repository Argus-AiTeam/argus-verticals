# chip_design

**Purpose:** modular digital ASIC/accelerator architecture and subsystem design,
with scoped studies/implementation and an optional complete delivery workflow.

Independent review and the `metric` completion gate remain. New tasks choose the
smallest matching profile: `architecture`, `rtl`, `verification`, `control`, `ppa`,
`prototype`, `benchmark`, a dependency-checked `custom` combination, or explicit
`full`. For example, `rtl + ppa` selects definition, architecture, environment,
RTL, verification and PPA without prototype/benchmark/final delivery. Manager
output explains requested, automatically required and excluded work.
Legacy no-profile tasks retain all
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
- `skills/manager/`, `skills/planner/`, `skills/engineer/`, `skills/reviewer/`.

Extras: none. Tests: `tests/skills/test_chip_design_vertical.py`.

## Bounded APB4 control

The opt-in `control` profile uses the existing verification stage for a bounded
single-clock register/timer/interrupt implementation, authorized RTL repair or
diagnosis. Its [original-input contract](control-contract.md) defines byte writes,
exact waits/errors, one-shot/periodic timer behavior and set-dominant W1C IRQ
semantics. This separate profile does not require accelerator memory models or
physical PPA records and does not migrate any legacy workflow.
The classifier-visible purpose explicitly identifies this self-contained scope:
for `apb4-timer-v1`, authorized RTL repair and generic synthesis counts belong to
`control`, not an expanded accelerator `custom rtl+ppa` workflow.

With Yosys and Icarus installed, run
`python -m argus_verticals.chip_design.run_control_reference /tmp/new-control-study`.
The destination must not exist. The runner verifies RTL and actual synthesized
Verilog against an independent Python state model for every declared parameter/
seed configuration, checks original generic-cell limits and preserves byte
copies, native models and raw samples. The read-only checker reruns the native
flow in a temporary directory. Store-only role prompts include the exact
interpreter/loader commands. See `tests/skills/test_chip_control.py` for deliberate
RTL failures, input/evidence tampering, boundary cases and profile acceptance.

Design/repair must pass; only a requested diagnosis may be accepted with real
engineering findings. Missing tools or incomplete evidence cannot become a
negative diagnosis. These are finite checks and generic Yosys cell counts, not
formal equivalence, physical timing/area/power, a complete SoC or silicon results.
Native process monitoring is shared with CDC without changing its limits.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).

Version 1.x requires Argus workflow composition (`VerticalContract.compose_workflow`)
and digital_circuit 1.x for the expanded library. Upgrade the framework first.
Old frameworks fail visibly; existing projects are not auto-migrated. These
skills do not install EDA tools, PDKs or proprietary licenses.
