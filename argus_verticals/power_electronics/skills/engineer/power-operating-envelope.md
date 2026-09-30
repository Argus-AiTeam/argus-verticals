---
name: Operating Envelope and Numerical Margins
description: "Preserve external operating requirements, fixed design choices, interacting tolerances and honest finite-sample conclusions."
---

# A nominal pass is not an operating-envelope result

Separate what the environment can vary from what the designer may choose.
Input voltage, initial/final load, temperature and component variation are
operating assumptions. A nominal capacitor choice or fixed PWM duty is a
design decision. Do not retune the circuit separately for each corner unless
the original physical controller explicitly provides that behavior.

State the original goal before computing anything. A diagnosis evaluates the
supplied design and may validly report noncompliance. A design task must find
one allowed design satisfying all declared samples and margins. Switching a
failed design task to diagnosis is a change of task, not successful completion.

# Choose meaningful samples

Cross independent axes to expose interactions, rather than varying one input
at a time. Source extremes affect conversion ratio and inductor ripple;
small capacitance raises ripple and changes transient response; load affects
damping, conduction mode and settling. Endpoint combinations can therefore
fail even if all one-at-a-time experiments look acceptable.

Do not call endpoints a guaranteed worst case for a nonlinear switched
converter. A conduction-mode transition, resonance or protection boundary
can occur between them. Add justified interior samples or a separate analysis
when those mechanisms matter. A finite Cartesian grid still proves only the
sampled statement. Correlated manufacturing parameters and probability/yield
require explicit joint models, not a Cartesian grid labeled Monte Carlo.

Use physical values and source attribution. Multiply nominal component
parameters by declared positive tolerance factors; use absolute Celsius
temperature, never a percentage of Celsius. Temperature in the current
adapter changes the native diode, not unspecified L/C/resistor coefficients,
core loss or a coupled self-heating model.

# Quantify useful headroom

For an observed value x in original interval [a, b], lower headroom is x-a
and upper headroom is b-x. Required reserves have the same physical unit.
A voltage 0.0004 V above the minimum is a numerical pass with little reserve,
not evidence of robust hardware operation. Do not round an actual negative
headroom into zero or move the original bounds to accept a preferred design.

Report the scenario and resolution with the smallest observed headroom on
each side. Distinguish a limit violation from a positive but insufficient
reserve. Retain all failing conditions, not only the first. Check every
acceptance metric at both resolutions with an explicit original delta bound;
mean-voltage agreement alone does not establish accurate ripple or peaks.

Coverage requires every planned scenario and resolution to finish with
valid measurements. Failed energy accounting, unsettled steady windows,
non-growing sample counts, failed refinement and missing native results
mean the conclusion is not established. They are not negative engineering
answers that a diagnostic goal can accept.

# Respect feasibility and preserve attempts

For an open-loop Buck, mean output varies roughly with duty times supply,
with load-dependent losses. If the allowed supply interval is broad and the
requested output band is narrow, no single fixed duty may satisfy both
endpoints. Demonstrate infeasibility or request a separately authorized
controller/model change; do not silently add feedback, narrow the envelope
or claim that a successful nominal retry solved the problem.

Use the supplied operating specification and the canonical native runner.
The current executor refuses oversized Cartesian grids rather than omitting
combinations. Retain unsuccessful native attempts before changing an allowed
design choice; preserve the original specification. A completed diagnosis
must explicitly distinguish task acceptance from engineering noncompliance.
