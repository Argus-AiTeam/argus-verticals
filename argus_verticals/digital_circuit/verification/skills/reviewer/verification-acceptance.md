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

For the `cdc` profile inspect the entire declared adapter inventory, native
Yosys stage/clock/reset/fanout findings and every Icarus phase/reset trace.
Run the profile-specific native replay checker from the execution project;
the generic simulation-matrix checker has a different input contract.
Check the original requirement goal: valid negative diagnosis is not a passing
design. Do not allow a structurally bad reset path merely because its ideal
digital waveforms pass. Explain excluded metastability, MTBF, placement, timing,
pulse/bus coherence and system-level reset recovery claims.
For multiple data paths inspect independent high/low patterns, not only
simultaneous toggles. Match structural findings to the named native cell/bit,
expected signal and observed connections; failed inspected paths are not
accepted chains. A timeout or output-budget stop is incomplete execution,
not a valid negative engineering conclusion.
