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

## Accelerator verification and continuation

Non-control verification receives the shared
[review contract](../hardware/shared/verification-review.md), not an APB4
execution recipe. The host runs the existing validator under the saved
profile, including custom RTL-manifest requirements, and supplies its result
to a read/search-only Reviewer. Record checks do not run a one-shot numerical
experiment, resume a stopped runtime or replace project-specific acceptance.

Keep weights, activations, accumulators, residuals and K/V precision distinct.
Preserve each project's oracle, original tolerances and legal Manager ownership;
an implementation check is not a numerical result or a hardware claim. Neither
new knowledge nor host checking automatically migrates a historical campaign.
The [accelerator record contract](verification-contract.md) is also injected
into all four verification roles. It preserves the legacy format while checking
every declared `source_hashes` entry, including evaluator dependencies rather
than only RTL. Malformed or duplicate bindings, duplicate JSON fields and
nonfinite numbers fail explicitly; commands require actual argv and integer
exit codes.

An optional `verification/PLAN.json` can declare `supporting_files` for the
original numerical contract, reference helpers and retained fixtures. A present
plan and its declared files must be included in `source_hashes`. Existing
projects without that JSON plan need no new manifest. This is not the
specialty's simulation/formal record format and does not create a new evaluator.
PPA/prototype/benchmark also check every declared binding; final completion
rechecks verification. Preserve historical records rather than rewriting old
bindings to satisfy a new check.

An operator name such as FP16 or G128 is not a complete numerical specification:
group versus full-reduction accumulation, bias placement, selected mode, signed
underflow zero and overflow behavior must match the original implementation
contract. CPU-only experiments keep their project-native lifecycle and
scientific acceptance; do not fabricate RTL to route them through this checker.

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

Final control completion additionally requires the Engineer's structured
`verification/CONTROL_REVIEW.md`; Reviewer checks it independently and does not
fill in missing deliverables. Its measured JSON summary must match replayed
evidence and all original configurations. Native `control.validate` remains
report-independent for implementation and diagnosis; the profile completion
checker enforces the final report. Semantic event counts and cycle witnesses,
including valid completed byte writes, prevent labels alone from establishing
coverage. Missing coverage cannot qualify as a negative diagnosis.
The existing Argus round-evidence hook independently runs this checker on the
host before review and supplies the result to the read/search-only Reviewer.
No Reviewer shell permission or Engineer-authored proxy execution record is
needed. The final completion gate remains enforced separately.
Existing accepted projects keep their installed provider and records; the
strengthened assessment requires fresh results rather than rewriting old ones.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).

Version 1.x requires Argus workflow composition (`VerticalContract.compose_workflow`)
and digital_circuit 1.x for the expanded library. Upgrade the framework first.
Old frameworks fail visibly; existing projects are not auto-migrated. These
skills do not install EDA tools, PDKs or proprietary licenses.
