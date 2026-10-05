# Bounded APB4 control evidence

Apply this contract only to the `chip_design/control` workflow profile. It uses
the existing `verification` stage for a self-contained implementation, authorized
repair or diagnosis. Other profiles and their nine-stage legacy full workflow
are unchanged. Do not manufacture accelerator memory models, physical PPA,
prototype or final delivery records for this profile.

## Original inputs

Create `verification/CONTROL_PLAN.json` containing exactly
`{"specification": "design/control-spec.json"}` (the original path may differ).
The external specification has exactly these fields:

```json
{
  "contract": "apb4-timer-v1",
  "goal": "design",
  "top": "control_reference",
  "sources": ["rtl/control_reference.sv"],
  "base_address": 1073745920,
  "max_generic_cells": 2000,
  "configurations": {
    "compact": {"counter_width": 8, "wait_cycles": 0, "seed": 1},
    "waited": {"counter_width": 16, "wait_cycles": 2, "seed": 7}
  },
  "limitations": ["Finite single-clock control checks; no physical PPA or SoC qualification."]
}
```

These numbers are examples, not permission to replace the user's limits.
Preserve every original configuration and limit. An implementation/repair goal
is `design` and must pass; `diagnose` may finish with a reproducible engineering
failure. An unavailable tool, unsupported declaration, failed native command or
incomplete trace is never a valid negative diagnosis. Authoring a plan or report
does not authorize changes to the external specification. If requirements do
not match this fixed contract, explain the mismatch rather than silently mapping
them to it. Do not convert an arbitrary peripheral into this contract.

The top exposes `PCLK`, active-low asynchronous `PRESETn`, `PSEL`, `PENABLE`,
`PWRITE`, 32-bit `PADDR`/`PWDATA`/`PRDATA`, four `PSTRB` bits, three `PPROT` bits,
`PREADY`, `PSLVERR` and `IRQ`, and parameters `COUNTER_WIDTH`, `WAIT_CYCLES`,
`BASE_ADDR`. Parameter/seed configurations must be distinct, two to eight total:
counter width 4..32, exact added access waits 0..3, integer seed 1..2147483647.
Base address is a 256-byte-aligned 32-bit address at most 0xffffff00. The original
generic-cell cap is an integer 1..20000, applied to each configuration.
At most 16 plain relative .v/.sv sources, 256 KiB combined; original specification
at most 64 KiB. Sources and specification are outside verification outputs.
Sources cannot use includes, macros, external data or simulation system tasks;
only timescale/default_nettype directives and clog2/bits functions are allowed.

## Fixed `apb4-timer-v1` semantics

One little-endian 32-bit APB4 peripheral, one positive-edge clock, no bridge or
bus master. SETUP (`PSEL=1, PENABLE=0`) precedes ACCESS (`PSEL=PENABLE=1`);
transfer completes only at a rising edge with `PREADY=1`. Address, direction,
write data, strobes and protection remain stable through ACCESS. Every transfer
has exactly WAIT_CYCLES access cycles with PREADY low before completion.
No bus write effects in SETUP or waiting cycles. Contiguous transfers retain
PSEL but return to SETUP between them. PPROT is accepted but does not filter
accesses; this contract has no privilege/security policy.

| Offset | Register | Access and reset |
| --- | --- | --- |
| 0x00 | CONTROL | RW bits 0 enable, 1 periodic; reset 0 |
| 0x04 | RELOAD | RW low COUNTER_WIDTH bits; reset 0 |
| 0x08 | COUNT | RO low COUNTER_WIDTH bits; reset 0 |
| 0x0c | STATUS | W1C bit 0 pending; reset 0 |
| 0x10 | MASK | RW bit 0 IRQ enable; reset 0 |
| 0x14 | SCRATCH | RW all 32 bits; reset 0 |

All other read bits are zero; writes to reserved bits have no effect. PSTRB[n]
selects PWDATA[8*n +: 8]; zero strobes make valid writes no-ops. COUNT writes,
unmapped addresses, high-address aliases and non-word-aligned addresses report
PSLVERR at completion, with no bus-induced state changes; invalid reads return
zero. COUNT writes remain errors even with zero strobes. Timer progression is
independent of unsuccessful bus transfers. No write response implies a stall.
PREADY outside ACCESS, PSLVERR outside completion and PRDATA outside completed
reads are not acceptance signals.

On each non-reset rising edge, use the **old** register state:
an enabled nonzero COUNT decrements; enabled COUNT=0 produces a timer event,
reloads old RELOAD if periodic, otherwise clears enable and leaves COUNT=0.
An accepted CONTROL low-byte write then overrides CONTROL; writing enable=1
loads old RELOAD into COUNT (including restart when already enabled). Writing
enable=0 does not undo that edge's timer count step. RELOAD writes affect future
loads, not the same edge's old-state timer event. Thus load N expires after N+1
subsequent enabled edges; periodic RELOAD=0 produces an event every enabled edge.
COUNTER_WIDTH truncates RELOAD and COUNT; no decrement below zero wraps around.

Pending is `(old_pending AND NOT accepted_W1C) OR timer_event`: **set dominates
clear**, so a same-cycle event is not lost. IRQ is `pending AND mask`; mask
changes do not clear pending. W1C observes bit 0 only with PSTRB[0].
Asynchronous reset clears all state, IRQ and wait progress, even mid-transfer;
the reset-aborted transfer does not commit. Release is externally synchronous
in this single-clock study; this is not a reset synchronizer/CDC qualification.

See the [Arm APB specification](https://developer.arm.com/documentation/ihi0024/latest)
for protocol background. The timer/register/zero-on-error policies above are
this explicit peripheral contract, not claims that APB prescribes those policies.

## Native execution and acceptance

The packaged runner generates legal finite APB transactions from original seeds,
not from DUT responses. Icarus samples responses before the transfer edge and IRQ
before/after it. A separate Python state model recomputes every consumed response
and IRQ observation. Cases include all 16 strobe masks, reserved/RO/invalid
accesses, back-to-back transfers, exact waits, single-shot/periodic/zero/max reload,
IRQ mask and W1C races, and asynchronous reset during traffic plus seeded traffic.
Only protocol-defined valid response windows are compared; X/Z in consumed
signals are mismatches. Logs retain every sample, not just a PASS string.

Yosys elaborates every original parameter configuration, flattens and synthesizes
with `-noabc`, checks the design, and emits the netlist, synthesizable Verilog and
JSON cell statistics. The flattened interface, no-latch constraint and original
generic-cell cap are checked. The synthesized Verilog is independently compiled
and run through the same stimuli and Python oracle: RTL passing alone is not
enough. This finite comparison is not formal equivalence or physical PPA.

`verification/control/RESULTS.json` retains actual commands, logs and independent
byte copies of all original inputs and generated evidence.
`ASSESSMENT.json` retains separate RTL/synthesized comparisons, first mismatches,
cell counts and original-cap headroom. No fresh execution overwrites an existing
control results directory. Preserve a failed attempt in a separately named
directory before repairing authorized RTL and rerunning; never rewrite its
records to manufacture success. Verification inputs and installed provider code
are not repair targets.

The read-only checker recomputes all assessments, then reruns the complete native
flow in a temporary directory and compares generated models, testbenches and raw
traces. It rechecks byte copies after replay. VVP executables are retained, but
process-specific compiled addresses are not claimed as byte-identical rebuilds.
Native commands have 30-second limits, the batch 240 seconds, and generated
top-level output is polled every 50 ms against 128 MiB (a stop threshold, not a
filesystem quota). Termination stops only the owned process group on POSIX and
retains actual exit codes and stop reasons.

Reviewer must inspect original constraints, meaningful coverage, oracle
independence and any repair diff, execute the profile-specific checker, and
explain finite-check limitations in `verification/CONTROL_REVIEW.md`. A native
tool exit zero, Engineer's report or generic cell count alone is not acceptance.
