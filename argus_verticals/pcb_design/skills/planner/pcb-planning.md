---
name: PCB Scope Planning
description: "Choose the smallest coherent PCB scope and retain independent acceptance requirements."
---

# Plan the requested physical question

Classify whether the request concerns requirements, a schematic/board change,
native diagnostics, manufacturing files or review. Select only the appropriate
profile or composed stages. Existing-project verification does not require a
new design, analog simulation, RF study or fabrication order.

List the available native inputs and missing project-local dependencies.
Determine whether ERC, DRC, schematic parity or exports are actually requested.
For exports identify layer set, units/origin and exact PTH/NPTH counts; do not
invent universal feature thresholds. Explain which requirements need human
review, device documents or physical measurements beyond native checks.

Check executable boundaries before scheduling work. Zones, advanced drill
structures and external library resolution are not silently converted into
the supported subset. Preserve the user's source-modification permission and
original numeric limits. Independent review must read the selected evidence,
not require unrelated stages to be completed.
