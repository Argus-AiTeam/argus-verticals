---
name: Independent Digital Verification Matrix
description: "Build executable requirement, configuration and failure matrices; use the bundled FIFO regression without mistaking counts for coverage closure."
---

# Independent comparisons and regression closure

Start from observable requirements, not the RTL's internal state machine.
For a FIFO, the reference model is a transaction queue; for a CSR block it is
an address-to-register model with access side effects; for DMA it is byte memory
plus accepted descriptors, outstanding requests and completion obligations.
Copying RTL transitions into the oracle can reproduce the design's defect.

Enumerate widths, legal depth extremes, non-power-of-two depths, reset timing,
traffic patterns and seeds before running. Choose a bounded justified matrix:
pairwise coverage reduces cases but does not establish full cross-product
coverage. Explicitly test illegal parameter rejection separately from legal
functional cases. Keep a first-failing seed and waveform, then minimize the
counterexample. Do not rename a failed case, remove it, or relax its tolerance
to get a successful run.

The reference `stream_fifo_tb.sv` samples transfers at the active edge before
nonblocking RTL updates. It models accepted transactions rather than comparing
the implementation's pointer/count state. Data comparison uses case inequality
to reject X/Z. Input payload and valid remain stable until acceptance; output
stability is checked across stalls. Reset discards outstanding transactions in
both models, and the check is repeated midstream. Directed fill/drain windows
guarantee boundary comparisons; seeded traffic exercises mixed behavior.

Run the module command documented in this vertical's README in a **new**
directory. Read every `CHECK` count and the 12 configuration records. A count
proves that comparisons executed, not that functional/code/assertion coverage
is sufficient. Add meaningful crosses such as reset-with-outstanding-work and
wraparound-with-backpressure when adapting the reference. Preserve testbench,
RTL, plan and tool arguments; compare input snapshots directly rather than
inventing freshness identifiers.

Before acceptance, deliberately break one observable behavior and demonstrate
that the oracle fails. Restore the correct source and rerun its affected cases.
This is a test-quality check, not permission to mutate an operator's production
source without consent. The repository tests mutate a private copied reference.
