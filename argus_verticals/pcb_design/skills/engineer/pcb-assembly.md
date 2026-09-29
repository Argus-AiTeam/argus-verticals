---
name: PCB Assembly and Verification Planning
description: "Connect board geometry to assembly access, inspection and bounded physical verification requirements."
---

# Assembly is a separate physical process

Distinguish bare-board fabrication from component assembly. Review polarity,
pin one, fiducials, tooling, component courtyard/height, stencil/paste needs,
connector accessibility and rework clearance. A board DRC cannot prove solder
joint formation or that a cable can be inserted in the assembled enclosure.

Pick-and-place rotations and origins are conventions that must match the
assembler. BOM designators, quantities, DNP options and approved variants must
agree with the assembly drawing and native design. These files are not produced
by this initial Gerber/drill adapter.

Provide accessible test points and a traceable inspection strategy for relevant
interfaces. Distinguish visual inspection, continuity checks, programmed
functional tests and environmental qualification. A schematic/board parity
report is not evidence of an assembled specimen.

Document missing physical evidence and responsible review requirements. Do not
infer permission to energize or operate hardware from file-level acceptance.
The executable reference is an unpowered continuity coupon, not a validated
product or instructional substitute for safe laboratory procedures.
