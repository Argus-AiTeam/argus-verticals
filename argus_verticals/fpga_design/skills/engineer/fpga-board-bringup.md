---
name: FPGA Board Bring-up
description: "Progress from safe board identification and clock/reset checks to measured traffic, logic-analyzer probes and host integration."
---

# Board behavior is a separate result

Before programming, confirm operator permission, board revision, FPGA part,
pinout, supply and I/O-bank voltages. Check for pin contention and load limits.
Use the board's documented current-limited low-voltage setup; do not improvise
high-voltage or high-current connections. A reference target JSON is not an
approved wiring diagram.

Start with power/clock/reset observations, then a deterministic small function.
Record device identity, programmed bitstream, transport and measurement setup.
A successful programmer exit establishes a transfer, not functional correctness.
An LED observation can check a clock divider but cannot validate DMA or memory
integrity. Predeclare measured quantities, units, limits and sample duration.

Add observability intentionally: counters for accepted/completed/aborted work,
sticky protocol-error bits, FIFO high-water marks and a build identifier that
comes from an explicit supplied version, not a new generated token. On-chip
logic analyzer triggers should target a specific suspected violation, with
clock domain and capture depth documented. Instrumentation consumes resources
and can alter timing; recheck the affected implementation.

For host integration, freeze register layout and side effects, interrupt
handling, DMA ownership, memory coherence and completion semantics. Stress
backpressure, reconnects, reset while busy and error recovery. Correlate host
transactions with device counters so an old response cannot be mistaken for
new work. Preserve measurement commands and raw device output.

The bring-up checker matches observations to finite limits and current
bitstream/target copies. Independent review must still establish that the
measurements came from the named device. If no board is connected, finish an
implementation scope only; never substitute simulation for physical results.
