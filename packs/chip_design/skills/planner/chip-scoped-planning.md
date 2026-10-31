---
name: Chip Scoped Planning
description: "Plan chip subsystem work against requested goals, required companion stages and current input evidence without silently expanding delivery scope."
---

# Plan within the resolved hardware scope

Read the workflow profile, requested goals and effective stages the Manager
named before proposing work (with none named, the profile is `full`). The
Manager owns scope selection; a Planner cannot remove mandatory companions or
insert prototype/final delivery merely because they appear in the full-flow
guide. Put the profile in every task so the Engineer and Reviewer run the stage
checks with the same `--workflow-profile` (and `--workflow-stages` for `custom`).

Separate subsystem decomposition from stage scheduling. For each selected
compute, memory/DMA, interconnect, clock/reset/power or host module, identify the
observable contract, reusable input, modification, independent oracle and raw
acceptance evidence. Use the digital topic guides (start from
`skills/engineer/digital-knowledge-map.md`) for the actual implementation
mechanisms.

Plan from the highest-risk unknowns and the declared delivery level. Close
workload/interface/quality ambiguity before architecture; close EDA/PDK/IP/license
readiness before RTL; require independent verification before PPA; and require
PPA/prototype evidence before benchmark claims. Rank architecture changes by
roofline/Amdahl leverage and end-to-end workload impact. Separate fair same-flow
open baselines from commercial market context. Replan when toolchain,
correctness, timing, area, power or memory bandwidth stands in the way rather
than polishing downstream reports.

For `rtl + ppa`, plan definition, architecture, environment, RTL, verification
and PPA in that order. Keep verification planning ahead of implementation even
though verification acceptance follows RTL. Do not plan prototype, benchmark
or final delivery artifacts. For PPA on existing RTL, establish the manifest,
specification/oracle, constraints and target inputs; do not invent an
architecture stage or silently start changing RTL.

Reuse current, accepted inputs rather than rebuilding by ceremony. Record why
they remain valid. Missing inputs, unavailable tools or changed requirements
are explicit blockers; tell the Manager when the requested scope must change.
Do not treat a report from another source revision as reusable.

Batch the remaining operators of one already-understood hardware family into one
definition/architecture contract; never schedule per-operator environment
refreshes when target, tools, IP, licenses and delivery level are unchanged. For
a non-milestone operator uplift, plan rtl -> verification and, when in scope,
target-matched PPA as exactly one bounded RTL task that includes implementation,
full regression, canonical PPA and evidence binding; do not open separate
verification or PPA closeout tasks. Leave prototype, full benchmark and the
signoff stage for complete-workload or model/system release milestones. Keep an
unmet operator-owned target unmet until the operator explicitly approves a
replacement; do not route implementation through a proposed cap.

Full delivery remains a set of target-level milestones, not a prohibition on
iteration. Plan small design/verification/PPA experiments with independent
review and a clear stopping criterion. Any change invalidates its downstream
evidence until refreshed; do not claim that changing a stage list automatically
revalidates results.
