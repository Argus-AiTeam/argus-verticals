---
name: "Digital Circuit Sign-off Review"
description: "Independently review Verilog/SystemVerilog designs for contract fidelity, simulation/formal correctness, synthesizability, timing constraints, and reproducible delivery."
---

# Digital Circuit Sign-off Review

Read the task's requested scope (see the
[knowledge map](../engineer/digital-knowledge-map.md)) before applying the
protocol below. Only selected stages and actual claims require their
corresponding evidence. A `specification` task needs a correct, reviewable
circuit explanation and specification, not invented RTL or simulation results.
An `rtl` task needs real RTL verification but not a synthesis/delivery bundle.
A verification-only task still requires executable existing RTL and an
independent oracle. Fixed external benchmarks retain their own harness
requirements regardless of these circuit scopes.

For a mixed request, review the requested goals and the complete stage list they
imply. RTL implies specification and verification; synthesis implies verification;
delivery implies the whole circuit workflow. Reject missing companions, missing
existing RTL and requested synthesis supported only by N/A notes. Reuse is allowed
only for evidence that still matches the actual design and claimed behavior.

## Review protocol

1. Read the original task and frozen hardware specification. Write down, for yourself, the interfaces, clock/reset behavior, cycle timing, parameters, edge cases, and required outputs the work must satisfy.
2. Inspect the actual RTL. Check assignment discipline, completeness, widths/signedness, reset state, counter/FIFO boundaries, state-machine recovery, clock-domain crossings, and simulation-only constructs.
3. Inspect the oracle and testbench independently. Turn back a reference model that merely duplicates the RTL or assertions that never activate.
4. Inspect the declared clean verification command, its raw pass/fail output and the result of this pack's check `python3 '<this folder>/evidence.py' verification --project-root .` (run from the project workspace; `<this folder>` is the pack directory). Never claim execution you did not perform, and do not accept Engineer prose as independent checking. Return missing or contradictory evidence for repair; preserve failing seeds/logs/waveforms. Fixed benchmarks retain their own execution and review mechanism.
5. Check directed boundary tests, randomized/exhaustive coverage appropriate to the design, reset transitions, stalls/backpressure, simultaneous events, and X/Z detection.
6. Read formal evidence property by property. A bounded or vacuous proof is not a universal proof.
7. For synthesis claims, inspect the actual tool/version, target, constraints, warnings, timing, utilization/area, latches, loops, undriven nets, and black boxes. A tool missing from the host PATH is no excuse when the project declares an already-local container toolchain.
8. Cross-check all reported values against raw logs and ensure generated outputs correspond to the submitted RTL revision.
9. Send the work back with one prioritized repair plan if any required behavior or claim is unverified.
10. Accept the work only when the selected scope is satisfied: a correct reviewable specification for knowledge-only work, or reproducible source and evidence for implementation/verification work. Never promote omitted stages into completed claims.

## What always sends the work back

- testbench/reference weakened to match the implementation;
- compile-only or waveform-only correctness claim;
- missing reset/clock/protocol semantics;
- unexamined latch, CDC, X/Z, width, or signedness hazard;
- fabricated or stale simulation, formal, coverage, timing, area, or power result;
- synthesis report without target/constraints, or timing claim without slack/clock context;
- private cache, undeclared file, or manual GUI state required for the claimed pass;
- unsupported behavior omitted from the final limitations.
- benchmark golden output, reference patch, or hidden harness exposed to the agent;
- first-attempt failures overwritten, omitted, or blended with post-repair success;
- official scores produced from a stale/empty patch, mutable evaluator, reused output prefix, or concurrent shared Docker harness.
