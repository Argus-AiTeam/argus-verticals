---
name: Chip Design Scope Selection
description: "Distinguish circuit work, hardware accelerator architecture and software kernels; choose and preserve the smallest complete chip workflow, with explicit full-flow support."
---

# Scope selection

Clarify the requested deliverable before selecting stages. "Accelerator" can mean
RTL/FPGA/ASIC hardware or software on an existing GPU/CPU. Ask which when the
request does not resolve it; do not infer CUDA/Triton from the word alone.

A single circuit/IP block and its local verification needs only this pack's
digital topic guides (`skills/engineer/digital-*.md`) with the `rtl` or
`verification` profile. The chip guides add compute/memory/interconnect/host
architecture and integration. Kernels executing on existing hardware are outside
this pack. An existing circuit repository and an explicit artifact request can
resolve the ambiguity without asking again.

## Workflow profiles

| Requested outcome | Profile | Required stages |
| --- | --- | --- |
| Compare or define accelerator architectures | `architecture` | definition, architecture |
| Implement and verify a hardware subsystem | `rtl` | definition, architecture, environment, rtl, verification |
| Verify existing chip RTL | `verification` | verification |
| Design, repair or diagnose the fixed `apb4-timer-v1` peripheral | `control` | verification |
| Evaluate existing design PPA | `ppa` | verification, ppa |
| Demonstrate an existing design on the declared target | `prototype` | verification, ppa, prototype |
| Measure existing design against baselines | `benchmark` | verification, ppa, benchmark |
| Complete target-level delivery and sign-off | `full` | all nine stages |

Choose the smallest complete matching profile or custom composition by default, not `full` merely
because the work concerns chips. Explicit "full flow", full IP delivery,
GDS/pre-tapeout/tapeout sign-off or equivalent end-to-end requests use `full`.
A PPA study *targeting* a process is not a request to tape out. For the fixed
`apb4-timer-v1` contract, `control` already includes authorized RTL repair,
native synthesis, both simulations and generic-cell limits; it is not a
`custom rtl+ppa` workflow.

## Composed tasks

When a preset is insufficient, choose `custom` with the requested goals, for
example `rtl` and `ppa`. The checks add mandatory companions; they do not
blindly execute the model's stage list.

| Operator request | Requested goals | Effective scope |
| --- | --- | --- |
| Create RTL and measure PPA, no board or release | `rtl;ppa` | definition, architecture, environment, rtl, verification, ppa |
| Architecture study with existing-design PPA | `architecture;ppa` | definition, architecture, verification, ppa |
| Audit tools without implementing hardware | `environment` | environment |
| Prototype and benchmark existing RTL | `prototype;benchmark` | verification, ppa, prototype, benchmark |
| Final target-level certification | `signoff` | all nine stages |

Request creation stages whenever implementing or changing that output; use
existing-design goals only when the necessary inputs exist. A conflict such as
"create RTL but do not verify" needs clarification, not a waived dependency.
See `references/workflow.md` for the complete rules.

Name the profile, and for `custom` the requested goals, in your letter to the
team, together with the automatically added obligations and the excluded work;
tell the operator the same. Every task and check uses that profile
(`--workflow-profile`, and `--workflow-stages` for `custom`). Selected stages are
real gates, not a Planner suggestion. Do not encode scope by marking other
stages skipped or by declaring them complete early.

## Boundaries

`delivery_level` in `CHIP_SCOPE.json` names the implementation target (`rtl_ip`,
`fpga`, `gds`, `pre_tapeout`, `tapeout`). The workflow profile names what this
task will accomplish toward that target. Architecture-only work may discuss an
FPGA target but may not claim a working FPGA. A verification-only task must
provide existing manifest/source/oracle evidence or remain blocked.

Preserve accepted upstream evidence when still applicable. Change the profile or
target only on the operator's request. Do not silently run additional stages
when prerequisites are missing. Explain the gap, requested scope change and
cost/tool implication. Record unknown budgets as questions rather than invented
acceptance thresholds. Never treat a Planner or Reviewer budget-reallocation
proposal as the operator's authorization to relax a numeric target.

When continuing an existing accelerator campaign, distinguish engineering
readiness from the scientific hypothesis. Preserve the native task/dependency
contract and get the operator's go-ahead before new scientific execution.
Do not map a project's numbered numerical stages onto this pack's stage
names, silently change its profile, substitute the bounded APB4 adapter, or
require physical implementation for a CPU-only numerical investigation.
If the requested claim is outside this pack's executable acceptance,
retain the project's existing bounded process rather than inventing evidence.

## Reuse and milestones

Reuse Reviewer-accepted upstream stages and reopen only the earliest stage whose
contract actually changed. Advancing the first unsupported operator within an
unchanged workload, delivery level, numerical contract, host/memory interface,
resource budget, architecture, target technology and toolchain is an RTL delta:
reopen RTL only. Reopen definition only for a real workload/delivery/interface/
budget contract change; architecture only for a changed dataflow, memory
hierarchy, compute organization or control interface; environment only for
changed target/tool/IP/license requirements. Do not rewrite or re-review stable
definition/architecture/environment records merely to replace the name of the
next unsupported operator. When several remaining operators share one descriptor
family, numerical contract, memory model and compute organization, freeze that
family once instead of reopening one contract per operator.

Use a fast capability loop for non-milestone operator uplifts: rtl ->
verification -> fresh target-matched PPA when in scope, as one bounded RTL task.
Run prototype, full benchmark, multi-node PPA, the signoff stage and a local
milestone commit only when the complete target hardware workload or complete
model/system demonstration is Reviewer-accepted, or the operator explicitly
requests a release. Intermediate operator groups such as QKV, RoPE+KV, Attention
or MLP are checkpoints, not release milestones. Every reused result must still
bind the current `design/RTL_MANIFEST.json` and sources through its
`source_copies`; stale bindings are never reusable.
