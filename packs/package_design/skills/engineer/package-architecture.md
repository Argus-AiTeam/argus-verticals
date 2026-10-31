---
name: Package Architecture Selection
description: "Compare package families against actual die, electrical, thermal and assembly requirements."
---

# Select against coupled constraints

State the required external interface, I/O count and pitch, signal bandwidth,
power delivery, heat removal, footprint/height, mechanical environment and
manufacturing constraints. Leaded, leadless, ball-grid, wafer-level and
multi-die approaches solve different interface problems; a package acronym
does not define a complete process or material set.

Compare die-to-package connections and package-to-board connections separately.
Wire-bond fan-out can impose perimeter and loop-height limits; flip-chip
redistributes connections but introduces bump/underfill and escape constraints.
Fan-out redistribution, interposers and embedded structures require explicit
process and assembly assumptions.

Document why a candidate is feasible and what remains unverified. Cost and
yield estimates require process, volume and supply-chain evidence rather than
generic constants. Thermal advantage cannot be inferred from package size
alone: the heat path, interfaces and cooling boundary matter.

Keep architecture reasoning distinct from executed evidence. An ideal
rectangular thermal model can compare declared conduction paths; it cannot
choose a manufacturable bump map or establish production reliability.
