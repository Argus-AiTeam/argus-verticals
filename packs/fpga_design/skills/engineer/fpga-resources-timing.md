---
name: FPGA Resources and Timing
description: "Design for BRAM/DSP/carry resources and real clock/I/O constraints; distinguish native Fmax evidence from full timing closure."
---

# Resources, constraints and implementation

Synthesis inference is target-dependent. A behavioral multiplier may map to
DSPs or LUTs depending on width, signedness, registers and enables. A memory
with asynchronous reads or unsupported collision behavior may become registers
instead of BRAM. Check native resource reports and synthesized structures;
source-level operator counts do not measure physical use. Record legal
read-during-write semantics and test them independently.

Do not reset every memory word merely for simulation convenience if that
prevents RAM inference. Reset the validity/control state and define when data
becomes meaningful. Pipeline arithmetic to the actual DSP register locations,
then account for the changed external latency and backpressure. Time sharing
saves resources only if muxing, control and memory bandwidth still satisfy
throughput and timing.

Freeze the base clock frequency, generated clocks, clock groups, input/output
delays and external interface budgets. Clock-enable logic is not a new clock.
Avoid general-logic clock gating; use the device's supported primitives.
Exceptions require a named reason and affected paths. A blanket false path can
hide a bug rather than fix it. Inspect unconstrained endpoints and constraints
that matched no object.

The first adapter checks native nextpnr utilization and single-clock Fmax,
including that the reported constraint matches the requested frequency. It
does not infer hold/CDC/I/O closure from that metric. Native tool reports,
source/configuration copies and the exact commands are part of the result;
changing pins, timing or RTL requires another affected implementation.

For Vivado or Quartus, future executable support must inspect their actual
clock, unconstrained-path, setup/hold, DRC and utilization outputs rather than
rename nextpnr fields. Until that adapter exists, keep such work in an explicitly
limited study, not a successful `implementation` result.
