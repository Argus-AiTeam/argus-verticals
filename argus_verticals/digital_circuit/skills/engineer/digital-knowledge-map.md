---
name: Digital Circuit Knowledge Map
description: "Choose detailed digital-design references by circuit topic and requested scope: logic, arithmetic, state, memories, protocols, CDC, timing, low power and verification."
---

# Digital circuit knowledge map

This is a reusable circuit library, not a requirement to build a complete chip.
First freeze observable behavior, then read the topic guides relevant to it.
Examples are deliberately small teaching blocks, not production-qualified IP.
Adapt reset, widths and timing to the actual interface contract.

## Topic map

| Topic | Design decisions and reference |
| --- | --- |
| Combinational logic | [Logic and encoding](digital-logic-encoding.md): Boolean reduction, priority, one-hot, hazards, complete assignments |
| Arithmetic | [Arithmetic and fixed point](digital-arithmetic.md): bit growth, signedness, saturation, rounding, multiplier structures |
| State and reset | [Sequential circuits](digital-sequential-reset.md): enables, reset styles, initialization, latency |
| Controllers | [FSMs](digital-fsm.md): state/output partition, transition completeness, recovery, liveness |
| Storage | [Memories and FIFOs](digital-memory-fifo.md): ports, collision modes, occupancy, non-power-of-two depth |
| Streaming | [Handshake pipelines](digital-handshake-pipelines.md): transfer events, elastic storage, stalls, skid buffers |
| Shared resources | [Arbitration and interconnect](digital-arbitration.md): fairness, ownership, credits, ordering |
| Clock boundaries | [CDC and RDC](digital-cdc-rdc.md): levels, pulses, buses, async FIFOs, reset release |
| Implementation | [Synthesis and timing](digital-synthesis-timing.md): inference, SDC, setup/hold, critical paths |
| Energy | [Clock enable and low power](digital-low-power.md): switching, gating cells, isolation, retention |
| Assurance | [Verification and formal](digital-verification-formal.md): independent models, properties, coverage, proof limits |
| Reuse | [Parameters and elaboration](digital-parameters.md): legal configurations, widths, generate branches |

Read existing RTL verification and error-guided repair skills for the exact
evidence formats. `chip_design` inherits this library; it adds system concerns
instead of duplicating these circuit fundamentals.

## Choose an outcome, not a compulsory full flow

The Manager saves a named `workflow_profile` in pipeline state. New tasks choose
the smallest sufficient profile from the menu; explicit full delivery uses `full`.

| Profile | Required stages | Typical request |
| --- | --- | --- |
| `specification` | specification | Explain an async FIFO and specify its interfaces |
| `rtl` | specification, rtl, verification | Build and verify a saturating counter |
| `verification` | verification | Add independent tests to an existing FIFO |
| `synthesis` | verification, synthesis | Compare two existing adder implementations |
| `full` | specification, rtl, verification, synthesis, delivery | Deliver reproducible, synthesized RTL IP |

Knowledge-only work records a reviewable `design/SPEC.md`, not invented simulation
results. A verification-only task still needs actual RTL, an independent oracle,
commands and raw results. Missing prerequisites block completion; they are not
permission to waive checks or silently broaden scope. Request a new handoff if
the intended deliverable changes. Projects without a saved profile retain their
previous full stage order.

## Reading and acceptance discipline

For each selected topic, record assumptions, alternatives, implementation,
failure cases and the evidence that distinguishes them. Separate logical
correctness from implementation quality: a simulator pass is neither a CDC
proof nor timing closure. Keep out-of-scope limitations visible; do not create
placeholder N/A reports for stages that the active profile omits.
