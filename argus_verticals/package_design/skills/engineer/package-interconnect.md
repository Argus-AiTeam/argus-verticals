---
name: Package Wire Bond and Flip-Chip Interconnects
description: "Reason about connection geometry, parasitics and electrical limits without claiming an extracted network."
---

# Follow signal and return together

Record pad/bump numbering, net assignment, dimensions, material, connection
method and reference directions. Wire length, loop height, spacing and return
geometry affect inductance and mutual coupling. Bump diameter, pitch, UBM,
redistribution and current-sharing geometry affect a flip-chip connection.

Rough R = rho L/A and V = L di/dt estimates can reveal sensitivities, but they
do not replace frequency-dependent extraction. Bond-wire arrays are coupled
structures, not automatically independent parallel inductors. Include the
return path and reference planes when interpreting any RLC or S-parameter model.

Current density, electromigration, fusing and temperature rise depend on
material/process, duty cycle, geometry and thermal conditions. Do not infer a
safe current rating from a wire or bump diameter alone.

Electrical extraction, high-frequency SI/PI, bump-map generation and physical
connection verification are not executed by the initial thermal backend.
Transfer explicit assumptions and outputs to an appropriate electrical tool
when the task requires them.
