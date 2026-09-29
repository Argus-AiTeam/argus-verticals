---
name: Filters, Poles and Transient Response
description: "Use independent RC and second-order reasoning, account for loading and initial conditions, and measure time/frequency behavior honestly."
---

# Predict before simulating

For an unloaded ideal RC low-pass, H(s)=1/(1+s*R*C),
fc=1/(2*pi*R*C), and the unit-step response is 1-exp(-t/(R*C)).
These provide independent expectations for magnitude, phase, cutoff and time
constant. Include source and load impedance before applying the simple formula:
loading changes both DC gain and effective resistance. Compare normalized
Vout/Vin when source amplitude is not exactly one.

For a second-order response, damping and natural frequency are separate from
the observed -3 dB point. Peaking, overshoot and settling depend on damping,
and a high-Q circuit may have multiple threshold crossings. Do not choose an
arbitrary first crossing and call it the unique bandwidth. Define the relevant
window and physical interpretation, and ensure it contains the required event.

Transient initial conditions are part of the experiment. A step source with a
finite edge has a different early response from an ideal mathematical step.
Record its delay and edge times, the initial capacitor/inductor state, whether
an operating-point solution was used, and the requested timestep/output range.
Do not use an initial-condition option simply to force a desired startup result.

The current reader linearly interpolates saved samples. Choose a grid fine
enough for the declared acceptance interval and check sensitivity to a finer
grid where interpolation could dominate. A transient sample after a nominal
settling time is not by itself a settling-time measurement: ringing may leave
the band later. Check the complete relevant tail or state the narrower claim.
The RC reference is intentionally first-order, linear and unloaded.
