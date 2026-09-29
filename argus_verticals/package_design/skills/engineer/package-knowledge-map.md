---
name: Semiconductor Package Knowledge Map
description: "Choose package-level electrical, thermal, mechanical and assembly reasoning without implying every topic has an executable solver."
---

# Begin at the die-to-system interface

Identify die count, dimensions, power map, pad interface, I/O requirements,
allowable envelope, assembly process, cooling path and reliability conditions.
A semiconductor package connects and protects dice; it is not interchangeable
with chip logic, transistor design or a PCB fabrication project.

- [Architecture selection](package-architecture.md): package families and coupled tradeoffs.
- [Die attach and interfaces](package-die-attach.md): bond layers, voids and contact assumptions.
- [Wire bond and flip chip](package-interconnect.md): connections, parasitics and process constraints.
- [Substrates and escape](package-substrates.md): redistribution, vias and reference paths.
- [Interposers and chiplets](package-advanced-integration.md): 2.5D/3D integration and system boundaries.
- [Thermal modeling](package-thermal.md): boundary conditions, units and model resistance.
- [Mechanical reliability](package-mechanics.md): expansion mismatch, warpage and fatigue.
- [Assembly and test](package-assembly.md): process evidence, inspection and qualification limits.
- [Native thermal execution](package-native-execution.md): Gmsh/CalculiX scope and evidence.

Use only the methods needed for the request. Knowledge breadth does not
authorize inventing PDK/process rules, material curves, vendor simulation data
or physical measurements. The initial executable backend owns a limited steady
thermal model, not a complete commercial package-design environment.
