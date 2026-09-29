---
name: Analog and Mixed-Signal Knowledge Map
description: "Navigate analog circuit reasoning by physical question, choosing only the models and analyses needed for the requested result."
---

# Choose the physical question before the tool

Start with the observable, its unit, excitation, loading and tolerance. A circuit
that passes one AC sweep is not automatically correct at startup, under overload,
at temperature extremes or in a sampled system. Conversely, a request for a
small-signal transfer function does not require inventing a complete board project.

Use these connected topics:

- [Bias and small-signal foundations](analog-bias-small-signal.md): operating region, loading and linearization.
- [Feedback and stability](analog-feedback-stability.md): return ratio, margins, compensation and misleading tests.
- [Amplifiers and op-amps](analog-amplifiers.md): headroom, gain, input/output limits and dynamic behavior.
- [Filters and transients](analog-filters-transients.md): poles, damping, step response and independent equations.
- [Noise and dynamic range](analog-noise-dynamic-range.md): spectral density, bandwidth and noise budgets.
- [Models, variation and numerical accuracy](analog-models-corners.md): provenance, valid ranges, corners and convergence.
- [Converters and interfaces](analog-converters-interfaces.md): acquisition, references, quantization and analog/digital boundaries.
- [Passives and physical sensitivity](analog-passives-physical.md): parasitics, leakage, coupling and what lumped models omit.
- [Ngspice execution and evidence](analog-ngspice-evidence.md): reproduce selected analyses and inspect native measurements.

Knowledge breadth is not executable coverage. This provider's current reader
supports operating point, single-variable DC, AC and transient data. It does not
certify noise analyses, RF electromagnetic behavior, extracted layout, foundry
corners or mixed-language co-simulation. When the missing method is essential,
state that limitation rather than renaming a different calculation as the answer.
