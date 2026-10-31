---
name: PCB Components and Footprints
description: "Connect the exact component variant, pin numbering, land pattern and assembly process."
---

# Exact variant, not approximate package name

Keep manufacturer part number, suffix, package code, voltage/temperature ratings
and assembly option explicit. A nominally identical package family can contain
different pad numbering, exposed-pad requirements or body tolerances. Cross-check
symbol pin numbers against footprint pad numbers and the component drawing.

Interpret dimension datums, tolerances, recommended land pattern, solder mask
and paste openings separately. Courtyard represents an assembly envelope, not
electrical clearance. Exposed thermal pads may have electrical functions and
specific paste-window/via recommendations. Do not invent those requirements.

Inspect pin-one/polarity indicators from the board's top/bottom assembly view,
and connectors from the actual mating side. Verify plated versus nonplated
holes, lead fit, annular ring and mechanical locating features. A native
footprint-library match only compares the local library: it is not a datasheet
certification.

Retain local symbols and referenced footprint files with the design. Record
source and revision of any external datasheet used; flag missing or ambiguous
drawings. Procurement/lifecycle alternatives need electrical and mechanical
re-evaluation, not just a matching purchasing description.
