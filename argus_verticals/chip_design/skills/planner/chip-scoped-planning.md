---
name: Chip Scoped Planning
description: "Plan chip subsystem work against requested goals, required companion stages and current input evidence without silently expanding delivery scope."
---

# Plan within the resolved hardware scope

Read the saved profile, requested goals and effective stages before proposing
work. The Manager owns scope selection; a Planner cannot remove mandatory
companions or insert prototype/final delivery merely because they appear in
the full-flow guide.

Separate subsystem decomposition from stage scheduling. For each selected
compute, memory/DMA, interconnect, clock/reset/power or host module, identify the
observable contract, reusable input, modification, independent oracle and raw
acceptance evidence. Use the inherited digital-circuit topic guides for the
actual implementation mechanisms.

For `rtl + ppa`, plan definition, architecture, environment, RTL, verification
and PPA in that order. Keep verification planning ahead of implementation even
though verification acceptance follows RTL. Do not plan prototype, benchmark
or final delivery artifacts. For PPA on existing RTL, establish the manifest,
specification/oracle, constraints and target inputs; do not invent an
architecture stage or silently start changing RTL.

Reuse current, accepted inputs rather than rebuilding by ceremony. Record why
they remain valid. Missing inputs, unavailable tools or changed requirements
are explicit blockers; ask for a new handoff if the requested scope must change.
Do not treat a report from another source revision as reusable.

Full delivery remains a set of target-level milestones, not a prohibition on
iteration. Plan small design/verification/PPA experiments with independent
review and a clear stopping criterion. Any change invalidates its downstream
evidence until refreshed; do not claim that changing a stage list automatically
revalidates results or schedules parallel work.
