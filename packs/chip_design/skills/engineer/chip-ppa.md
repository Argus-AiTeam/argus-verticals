---
name: Chip PPA and Physical Tradeoffs
description: "Evaluate accelerator PPA under matched targets and constraints, distinguish synthesis/post-route/silicon evidence, and choose Pareto improvements without overstating results."
---

# PPA and physical tradeoffs

## Comparison contract

Freeze target FPGA or PDK/library/corner, tool revision, clock/I/O constraints,
memory implementation, utilization, activity assumptions and workload. Sky130 is
one possible target, not a universal default. Never compare another process
against Sky130 and present the difference as an RTL optimization gain.

Separate analytical estimates, synthesis, placement, routed extraction and
measured silicon/board results. Each answers a different question. A synthesis
frequency estimate cannot establish routed timing; board power includes components
outside the accelerator unless measured and attributed otherwise.

## Explore meaningful alternatives

Evaluate lanes, folding, buffer sizes, banking, pipeline depth, arithmetic width,
resource sharing and dataflow. Change one interpretable architectural dimension
at a time where possible, but recognize interacting tradeoffs. Keep correctness
constant and record configurations. Stop tiny local tweaks when gains saturate;
revisit memory traffic, utilization or sharing rather than gaming a single metric.

Track a Pareto table: area, frequency, cycles, memory, power/energy, correctness and
limitations. A higher clock with more cycles may worsen latency; smaller area
with much lower throughput may violate the requested budget. Do not collapse
metrics into an invented score unless the operator chose that objective.

## Physical implementation

Inspect congestion, fanout, placement locality, macro interfaces, clock tree and
timing path composition. SRAM placement and pin access can dominate a design that
looks small in RTL. Consider hold as well as setup and document unconstrained
paths. For physical delivery preserve extraction, STA, DRC/LVS and the target's
additional checks, not only a GDS filename.

## Evidence and scope

Use `ppa/PROTOCOL.md` and the existing structured results schema with current
sources, constraints and raw reports. If power is not measured, use the schema's
explicit unmeasured reason; never substitute a guess as measured watts.
Physical delivery levels retain their stronger evidence requirements.

A `ppa` profile verifies existing RTL and closes its PPA gate without requiring
an FPGA demo or benchmark marketing comparison. Full delivery still runs the
remaining selected-target gates. Missing tools block the requested measurement;
they do not justify changing the target or quietly reporting an estimate as a run.
