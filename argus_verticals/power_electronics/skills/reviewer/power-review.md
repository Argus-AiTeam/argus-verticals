---
name: Independent Power Review
description: "Check actual topology, units, source signs, transient energy, numerical resolution and claims."
---

# Review the native study, not its summary alone

Read the circuit, saved waveform and native completion diagnostics against
the original model and plan. Check winding/rectifier orientation, switch timing,
initial conditions, load conductance and measurement-window membership.

Read the current host-executed checker result and inspect its recomputed
time-weighted means, RMS values, extrema and source/load/loss/storage balance.
Independently examine the equations and selected observation windows.
Reviewer is read/search-only; do not claim shell execution or use an
Engineer-authored Reviewer run in place of missing or failed host evidence.
Negative source current is expected when a voltage source supplies
power. Input/output inequality during startup is not automatically loss.
Inspect first/last-cycle agreement before calling an interval steady.

Verify smaller maximum steps actually generated more native samples and
the declared comparisons passed without relaxing original limits.
Keep known simplifications visible: omitted device charge/recovery, magnetic
effects, control, layout and thermal coupling cannot be certified by these
waveforms. Request focused corrections while preserving settled numerical
evidence; a completed report is not permission for physical operation.

For operating-envelope work, inspect the separate original specification.
Verify the Cartesian product plus nominal, a common design across corners,
both resolutions for every scenario, and explicit comparisons for every
checked quantity. Inspect the recomputed worst observed headroom and its actual
scenario; a nominal pass does not excuse a failing combination.

Read engineering status separately from task acceptance. A valid diagnostic
conclusion may be "requirements not met"; a design task may not complete on
that basis. Missing coverage, invalid physical measurements and failed
refinement invalidate either conclusion. The goal and original limits must
not have been changed after seeing failures.
