---
name: RF Impedance Matching
description: "Derive matching targets independently, distinguish source/load references from physical terminations, and assess practical bandwidth and loss limitations."
---

# Match a specified load at a specified operating condition

For real R0 and load ZL, reflection is (ZL-R0)/(ZL+R0). Smith-chart coordinates
depend on the normalization; changing the chart's R0 is not adding a matching
component. State which port is driven and how every other port is terminated
before interpreting return loss or delivered power.

For RL greater than RS, one low-pass L-match uses Q=sqrt(RL/RS-1),
series reactance X=Q*RS and load-side shunt susceptance B=Q/RL.
At the design frequency, choose L=X/(2*pi*f) and C=B/(2*pi*f).
Check topology orientation: reversing the same series/shunt order generally
does not implement the same transformation. Negative reactances may require a
different topology rather than a negative-valued passive component.

Use independent input-impedance or ABCD equations to check the result.
In the two-port representation, S11 assumes the output is terminated in its
declared reference impedance. A 50-to-100 ohm matching claim therefore needs
the correct termination/reference interpretation, not an arbitrary all-50-ohm
plot. Ideal losslessness should agree with a full-matrix power comparison.

Single-frequency matching does not establish useful bandwidth. Component Q,
self-resonance, parasitics, tolerances and load variation can dominate practical
performance. The bundled L-match is an ideal linear model, not a component
selection, power-rating check, nonlinear amplifier match or manufactured layout.
