---
name: Reproducible RF Network Execution
description: "Use the canonical network graph and real scikit-rf execution, preserve failures, and verify exported Touchstone data against independent expectations."
---

# Execute a bounded network question

Read the canonical record contract already included in the role context.
Create `rf/PLAN.json` from the actual request, not from fitted bounds around
an observed answer. Declare only the needed studies and dependencies. A
Touchstone-only inspection does not require creating a matching network,
and full scope does not require every operation the adapter supports.

Check physical port labels and wave references before joining networks.
Cascades connect two-port sections from left to right and require identical
frequency samples and equal reference impedances at their junctions.
Renormalization and port permutation must be explicit graph nodes. RLC
and line sections are ideal models, not extracted geometries.

Use the supplied runner. It calculates from copied inputs, exports Touchstone
2.0 results with explicit references, preserves independent output copies,
and recomputes bounded measurements. The checker also compares exported
matrices against a fresh calculation from the current inputs. This catches
stale, changed or inconsistent output, but not every modeling misconception.

Inspect failures rather than changing tolerances to make them disappear.
Preserve the old result directory before a justified rerun. Do not simply
refresh snapshots around old files. Numerical examples should be checked
against independent equations, and manufactured/measured claims require
their own evidence. Reviewer checks remain necessary even after the
read-only command returns an empty issue list.
