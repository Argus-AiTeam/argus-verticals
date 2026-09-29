---
name: Independent Verification Acceptance
description: "Review oracle independence, executed configuration identity, assumptions and witnesses beyond machine-readable result consistency."
---

# Review the actual checks

Inspect the plan and testbench, not just the final result. Match parameter and
seed labels to compile/run arguments. Verify that each counter increments only
after its associated comparison, that failures terminate execution, and that
the oracle does not copy the DUT algorithm. Check X/Z handling and reset epochs.
Require a demonstrated detection of an intentionally broken private example
when introducing a new scoreboard. For formal results inspect assumption
strength, the property harness and cover witnesses; preserve the bounded versus
inductive distinction. Current input snapshots establish consistency, not
authenticity or sufficient coverage. Do not approve missing CDC/STA/physical
claims based on simulation alone.
