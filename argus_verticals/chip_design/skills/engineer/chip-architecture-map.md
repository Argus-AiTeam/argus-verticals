---
name: Chip Architecture Knowledge Map
description: "Organize accelerator design by compute, memory/DMA, interconnect, clock/reset/power, host/compiler, verification and implementation tradeoffs."
---

# Chip architecture knowledge map

This library covers system and subsystem decisions. For bit-level arithmetic,
FIFOs, FSMs and CDC structures, read the inherited **Digital Circuit Knowledge
Map** rather than replacing it with generic chip advice.

| Subsystem | Read for |
| --- | --- |
| [Compute and numerics](chip-compute.md) | Workload mapping, dataflow, utilization, precision and folding |
| [Memory and DMA](chip-memory-dma.md) | Capacity/traffic models, banks, buffering, bursts and ownership |
| [Interconnect and integration](chip-interconnect.md) | Topology, ordering, arbitration, deadlock and integration contracts |
| [Clock, reset and power](chip-clock-reset-power.md) | Domain inventory, reset epochs, power sequencing and implementation constraints |
| [Host and compiler interface](chip-host-runtime.md) | Register/descriptor ABI, driver ownership, layout lowering and error recovery |
| [Verification architecture](chip-verification.md) | Unit/system oracles, differential testing, scoreboards and evidence reuse |
| [PPA and physical tradeoffs](chip-ppa.md) | Matched comparisons, target-specific tools, Pareto choices and physical limitations |

## Contract decomposition

For each included subsystem, specify inputs/outputs, timing/ordering, capacity,
ownership, failure behavior and reset semantics. Create a dependency table:
which assumption in one module is guaranteed by another. This catches gaps such
as "DMA never stalls" on the compute side and "consumer always accepts" on the
memory side.

Start with one representative workload and an independent model. Add a narrow
working increment: issue one command, move one tile, compute one result, return
one completion. Then expand shapes, overlap and parallelism. A coherent small
system is preferable to disconnected placeholder modules.

## Profile-aware artifacts

Only stages in the active profile require artifacts. An `architecture` result
contains a quantitative model and tradeoff analysis, not fabricated RTL or PPA.
An `rtl` result ends after independent verification; synthesis, prototype and
sign-off are not implied. Existing-design profiles must validate their source
and target prerequisites, even when they do not recreate the architecture.

The environment-first guide remains the detailed stage checklist; its steps are
conditional on the active profile. A full workflow is still available and retains
the target-level evidence requirements.
