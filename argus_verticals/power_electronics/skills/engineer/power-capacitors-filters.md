---
name: Capacitors and Power Filters
description: "Charge balance, adaptive-waveform RMS, ESR/ESL, input filters and resonances."
---

# Measure the current that actually charges the capacitor

For a linear capacitor, dv/dt=i/C and energy is C*v^2/2.
In a Buck stage capacitor current is the difference between inductor and load
current; in Boost operation the rectifier conducts only part of the cycle.
Use the appropriate waveform rather than recycling Buck ripple estimates.

Separate capacitance-related ripple from ESR steps and ESL overshoot.
DC bias, temperature and aging can substantially change effective capacitance.
RMS current must be integrated over time; adaptive simulator sample averages
are not time averages and over-weight dense switching-edge samples.

Input and output filters can interact with converter control and negative
incremental input impedance. Check damping and source impedance, not merely
nominal attenuation. The initial native model includes constant C and ESR,
but not ESL, bias dependence, aging or a synthesized input filter.
