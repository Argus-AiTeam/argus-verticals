---
name: Digital Verification Scope Selection
description: "Select the independent verification specialty without recreating RTL or silently adding formal, synthesis, or physical work."
---

# Select the requested assurance work

Use this specialty for an existing design's test plan, regression infrastructure,
protocol scoreboard or explicit formal check. For creating circuit RTL, select
the parent's RTL scope; for fixed external benchmarks use the benchmark child.
Keep `simulation`, `formal`, `cdc`, and `full` distinct. The `cdc` profile uses
only the simulation stage with its own CDC_PLAN and original domain specification;
do not create a FIFO matrix, formal results or board target for CDC-only work.
It checks bounded level/reset adapters, not complete CDC/RDC sign-off.
Combine the two general execution
stages with `custom` when both methods are requested but no complete review
package is requested. The selected execution stage still requires a plan
manifest; reuse an applicable one or materialize it from the supplied requirements
without adding a standalone planning stage. The always-present evidence contract
defines the record formats; do not substitute a prose summary for those records.
Existing plans and sources are not evidence that execution has happened. Missing tools prevent the corresponding
claim; they do not justify a fabricated successful result.
