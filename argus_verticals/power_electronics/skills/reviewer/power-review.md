---
name: Independent Power Review
description: "Check actual topology, units, source signs, transient energy, numerical resolution and claims."
---

# Review the native study, not its summary alone

Read the circuit, saved waveform and native completion diagnostics against
the original model and plan. Check winding/rectifier orientation, switch timing,
initial conditions, load conductance and measurement-window membership.

Recompute time-weighted means, RMS values, extrema and source/load/loss/storage
balance. Negative source current is expected when a voltage source supplies
power. Input/output inequality during startup is not automatically loss.
Inspect first/last-cycle agreement before calling an interval steady.

Verify smaller maximum steps actually generated more native samples and
the declared comparisons passed without relaxing original limits.
Keep known simplifications visible: omitted device charge/recovery, magnetic
effects, control, layout and thermal coupling cannot be certified by these
waveforms. Request focused corrections while preserving settled numerical
evidence; a completed report is not permission for physical operation.
