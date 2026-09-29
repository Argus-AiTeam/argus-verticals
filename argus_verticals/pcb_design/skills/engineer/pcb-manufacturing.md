---
name: PCB Manufacturing Preparation
description: "Check complete layer sets, coordinate conventions, hole types and physical limitations of fabrication files."
---

# A generated file is not an approved manufacturing package

Identify board revision, units, absolute/plot origin, layer order, copper count,
polarity, mask/paste/legend choices, outline and cutouts. Compare exported
geometry against the native board, including holes, copper-to-edge distances
and bottom-side interpretation. Avoid accidental mirroring or unit conversion.

Keep plated and nonplated drill types explicit. Drill diameter, finished-hole
diameter and routing/slot instructions differ. Empty NPTH output may be correct
when zero NPTH holes are intended; a nonempty filename alone does not prove
any hole exists. Verify count and coordinates, not only command return codes.

The initial backend emits Gerber X2 with explicit layers and Excellon decimal
millimetres at the absolute origin. It compares the full regenerated contents
apart from generation timestamps. A Gerber drawn-feature count is a structural
check, not an area, continuity or manufacturability calculation.

Fabricator-specific material, finish, tolerance, impedance, panelization,
testing and documentation requirements remain explicit external requirements.
Do not upload a project, place an order or claim universal DFM acceptance from
a successful native export.
