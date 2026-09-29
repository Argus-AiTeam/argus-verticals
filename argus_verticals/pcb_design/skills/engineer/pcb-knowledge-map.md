---
name: PCB Engineering Knowledge Map
description: "Choose the relevant PCB discipline without forcing a complete board-development workflow."
---

# Start with the physical board and requested question

Identify the design revision, intended function, interfaces, voltage/current
domains, mechanical envelope, fabrication process and expected outputs. An
existing board check needs its native design and acceptance conditions, not a
new schematic, simulation campaign or procurement exercise.

- [Schematic intent](pcb-schematic.md): pins, nets, power and electrical rules.
- [Components and footprints](pcb-components.md): actual package dimensions, pin mapping and lifecycle.
- [Stackup and constraints](pcb-stackup.md): material, copper geometry and manufacturing limits.
- [Placement and routing](pcb-layout.md): connectivity, clearance and return continuity.
- [Power and thermal](pcb-power-thermal.md): distribution, losses and thermal paths.
- [Mixed-signal and fast interfaces](pcb-signal-integrity.md): edge rate, reference planes and coupling.
- [Manufacturing preparation](pcb-manufacturing.md): output layers, origins, holes and board outline.
- [Assembly and verification](pcb-assembly.md): polarization, access, test points and physical limits.
- [Native execution](pcb-native-execution.md): supported KiCad inputs, reports and reproducibility.

PCB design concerns physical interconnection on a board. An RF matching study,
semiconductor package escape analysis or power-converter control model may
supply constraints, but is not silently solved by board ERC/DRC. Record where
cross-domain evidence is needed and preserve its assumptions.
