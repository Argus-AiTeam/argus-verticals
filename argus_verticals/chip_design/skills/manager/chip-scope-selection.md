---
name: Chip Design Scope Selection
description: "Distinguish circuit work, hardware accelerator architecture and software kernels; choose and preserve the smallest complete chip workflow, with explicit full-flow support."
---

# Scope selection

Clarify the requested deliverable before selecting stages. "Accelerator" can mean
RTL/FPGA/ASIC hardware or software on an existing GPU/CPU. Ask which when the
request does not resolve it; do not infer CUDA/Triton from the word alone.

Use `digital_circuit` for a circuit/IP block and its local verification. Use
`chip_design` for compute/memory/interconnect/host architecture and integration.
Use software kernel verticals for kernels executing on existing hardware.
An existing circuit repository and an explicit artifact request can resolve the
ambiguity without asking again.

## Workflow profiles

| Requested outcome | Profile | Required stages |
| --- | --- | --- |
| Compare or define accelerator architectures | `architecture` | definition, architecture |
| Implement and verify a hardware subsystem | `rtl` | definition, architecture, environment, rtl, verification |
| Verify existing chip RTL | `verification` | verification |
| Evaluate existing design PPA | `ppa` | verification, ppa |
| Demonstrate an existing design on the declared target | `prototype` | verification, ppa, prototype |
| Measure existing design against baselines | `benchmark` | verification, ppa, benchmark |
| Complete target-level delivery and sign-off | `full` | all nine stages |

Choose the smallest complete matching profile or custom composition by default, not `full` merely
because the vertical covers chips. Explicit "full flow", full IP delivery,
GDS/pre-tapeout/tapeout sign-off or equivalent end-to-end requests use `full`.
A PPA study *targeting* a process is not a request to tape out.

## Composed tasks

When a preset is insufficient, emit `WORKFLOW_PROFILE=custom` and requested goals
as `WORKFLOW_STAGES=rtl;ppa` (JSON uses a list). The host includes mandatory
companions; it does not blindly execute the model's stage list.

| Operator request | Requested goals | Effective scope |
| --- | --- | --- |
| Create RTL and measure PPA, no board or release | `rtl;ppa` | definition, architecture, environment, rtl, verification, ppa |
| Architecture study with existing-design PPA | `architecture;ppa` | definition, architecture, verification, ppa |
| Audit tools without implementing hardware | `environment` | environment |
| Prototype and benchmark existing RTL | `prototype;benchmark` | verification, ppa, prototype, benchmark |
| Final target-level certification | `signoff` | all nine stages |

Request creation stages whenever implementing or changing that output; use
existing-design goals only when the necessary inputs exist. Explain the
requested goals, automatically added obligations and excluded work before the
handoff. A conflict such as "create RTL but do not verify" needs clarification,
not a waived dependency. See `references/workflow.md` for the complete rules.
The framework exposes the resolved explanation in Manager output and events;
it does not add an interactive confirmation dialog or guess consent.

Return `WORKFLOW_PROFILE` with the Manager's vertical decision. The framework
saves the profile, custom requested goals and exact effective stage order. Selected stages are real gates,
not a Planner suggestion. Do not encode scope by marking other stages skipped
or by requesting direct early completion. Existing projects with no profile
retain their legacy full workflow; upgrading the plugin does not migrate them.

## Boundaries

`delivery_level` in `CHIP_SCOPE.json` names the implementation target (`rtl_ip`,
`fpga`, `gds`, `pre_tapeout`, `tapeout`). The workflow profile names what this
task will accomplish toward that target. Architecture-only work may discuss an
FPGA target but may not claim a working FPGA. A verification-only task must
provide existing manifest/source/oracle evidence or remain blocked.

Preserve accepted upstream evidence when still applicable. Use a new operator
handoff to change the profile or target. Do not silently run additional stages
when prerequisites are missing. Explain the gap, requested scope change and
cost/tool implication. Record unknown budgets as questions rather than invented
acceptance thresholds.
