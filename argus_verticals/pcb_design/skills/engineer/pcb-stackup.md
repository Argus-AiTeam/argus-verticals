---
name: PCB Stackup and Constraints
description: "Define actual layer geometry and manufacturer limits before relying on impedance or clearance claims."
---

# Stackup is a physical specification

State layer count/order, signal/reference assignment, finished thickness,
dielectric material and thickness, copper weight/finished thickness and relevant
loss/tolerance assumptions. Generic FR-4 is not a unique permittivity or loss
model. Controlled impedance needs a geometry/material calculation and often
fabricator adjustment; a width label alone proves nothing.

Separate electrical minimum clearance, fabrication minimum spacing and assembly
requirements. Use the applicable voltage/environment/material rules for
insulation design; do not invent creepage/clearance from a low-voltage DRC
default. Edge plating, board-edge clearances and slots affect physical paths.

Declare permitted via structures, drill sizes, annular rings, aspect ratios,
copper-to-edge distances and mask-web limits from the intended process.
Blind/buried/microvia structures are not interchangeable with through vias.
Rigid-flex, embedded structures and specialized finishes need their own process
specifications, not generic PCB assumptions.

The initial native backend checks existing planar geometry and explicit project
rules. It does not compute characteristic impedance or certify the full
stackup; zones and advanced drills require a different execution method.
