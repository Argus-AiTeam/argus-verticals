---
name: Power Analysis Planning
description: "Translate converter requirements into model closure, timed studies, checks and native refinement."
---

# Plan observable circuit behavior

Freeze topology, component sources, input conditions, PWM timing and load
behavior before execution. Declare original bounds and meaningful observation
windows rather than choosing a convenient interval after seeing the trace.

Distinguish startup, steady ripple and load-step response. Include stored
energy in transient power accounting. Establish continuous conduction before
using a CCM equation, and state the approximation behind any independent
reference; an averaged relation is not a transient waveform.

Budget native sample counts and retain failed attempts. Pair each study with
a smaller maximum step and compare the quantities that matter to the user's
question, including relevant excursions and ripple, not only mean output.
If a requested physical effect is outside the adapter, explain that boundary
without turning unrelated knowledge into an executable claim.
