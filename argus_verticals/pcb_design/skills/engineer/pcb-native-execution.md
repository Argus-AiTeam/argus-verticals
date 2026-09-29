---
name: Native KiCad Evidence
description: "Use the canonical PCB contract and actual native tools while preserving the original project and failed attempts."
---

# Use the selected native operations

The role prompt includes the authoritative `pcb/PLAN.json` schema and Store-safe
execution/checker commands. Do not substitute a similar schema, generated PASS
string or manual result record. Set initial acceptance from the user's request
and actual design, not from whichever report happens to pass.

Resolve the project, selected root schematic/board, hierarchical sheets, local
libraries and optional rules before execution. Root filenames must share the
project stem so KiCad loads the right settings. Preserve library identities;
an embedded footprint does not eliminate the need to retain the library used
by native consistency checks.

ERC/DRC exit 5 records actual findings. Inspect errors, warnings, exclusions,
unconnected items and requested parity results separately. Retain failed
outputs; repair only an authorized design issue, and preserve the previous
results before rerunning. Never suppress a rule to turn a defect into success.

The verifier reruns native commands in a temporary copy and checks geometry and
reports against current sources. It is read-only with respect to the project,
not a text-only heuristic. Unavailable KiCad or an unsupported design subset
must remain an explicit failure, never a successful fallback.
