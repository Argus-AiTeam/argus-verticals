---
name: Native Converter Execution
description: "Use real ngspice, current input copies, bounded resources and time-weighted waveform checks."
---

# Use the canonical circuit contract

The role context supplies exact model/plan schemas and Store-safe execution
and checking commands. Preserve original inputs and limits. Use the native
runner; averaged equations are independent checks, never replacement waveforms.

Observe startup, periodic steady behavior and load changes in distinct
declared intervals. Native transient initial conditions produce the first
saved point after zero; do not invent an initial waveform row or extrapolate
a measurement outside the saved interval.

The runner uses Gear integration, explicit tolerances and maximum time steps.
Numerical damping and missed extrema still require refinement checks.
Inspect actual sample growth and the relevant peak/ripple metrics, not just
a successful exit or a nearly unchanged mean.

Retain native circuit, ASCII waveform and logs. Runaway timestep collapse
must fail visibly under the time/output-size limits, with its failed attempt
preserved. The checker independently reruns ngspice in temporary directories;
existing results are not silently replaced, and the project remains unchanged.
