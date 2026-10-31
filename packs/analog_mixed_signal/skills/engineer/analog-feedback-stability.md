---
name: Analog Feedback and Stability
description: "Distinguish closed-loop response from loop return ratio, preserve bias during injection, and qualify stability conclusions."
---

# Define the loop and its sign

Write the feedback equations with explicit polarity. For the conventional
negative-feedback definition, Acl = A/(1+A*beta). A large DC loop gain reduces
gain error but does not establish stability. Extra poles, zeros, transport delay,
capacitive loading and frequency-dependent feedback can change the result.

A closed-loop Bode plot is not the loop return ratio. Do not label its phase
at its own bandwidth as phase margin. Measure return ratio using a justified
injection arrangement that preserves the operating point and the loading at
the break; a naive open circuit can change the system being measured. State
which loop is opened when several loops interact. The current adapter can read
the resulting AC vectors, but it cannot decide whether an injection topology
correctly measures the intended loop.

Gain and phase margins depend on crossover definitions and may be ambiguous
with multiple crossings. Inspect the full frequency response, not one selected
point. The reader intentionally refuses non-unique crossings inside a declared
window. Phase unwrapping needs sufficiently dense samples and becomes undefined
at a zero response. Increase resolution based on numerical error, not to hide
an inconvenient crossing.

For a one-pole model, the expected closed-loop pole is fp*(1+A0*beta).
Use that as a model-level check, then distinguish it from a practical amplifier
with additional dynamics. Small-signal stability, startup, overload recovery and
slew-limited settling are different questions. A tidy step trace alone does not
prove robustness over loads, supply conditions or device variation.
