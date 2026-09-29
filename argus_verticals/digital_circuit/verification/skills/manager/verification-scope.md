---
name: Digital Verification Scope Selection
description: "Select the independent verification specialty without recreating RTL or silently adding formal, synthesis, or physical work."
---

# Select the requested assurance work

Use this specialty for an existing design's test plan, regression infrastructure,
protocol scoreboard or explicit formal check. For creating circuit RTL, select
the parent's RTL scope; for fixed external benchmarks use the benchmark child.
Keep `simulation`, `formal`, and `full` distinct. Combine the two execution
stages with `custom` when both methods are requested but no complete review
package is requested. Existing plans and sources are prerequisites, not evidence
that their execution has happened. Missing tools prevent the corresponding
claim; they do not justify a fabricated successful result.
