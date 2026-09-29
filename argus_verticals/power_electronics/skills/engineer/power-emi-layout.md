---
name: Power Layout and EMI Constraints
description: "Commutation loops, common/differential-mode currents, sensing and separation from PCB qualification."
---

# Identify the rapidly changing current path

Trace commutation loops in each switch state, including local decoupling and
return conductors. Parasitic inductance converts di/dt into overshoot; switch
node capacitance and dv/dt drive displacement current and common-mode paths.
Schematic node equality does not establish low physical impedance.

Separate power returns from sensitive sensing paths deliberately. Kelvin
connections, coupled paths and reference placement matter to current sensing
and drive behavior. A filter may add a resonance or redirect noise rather
than eliminate it; include source/load impedance and damping assumptions.

Board layout and manufacturing checks belong to PCB work, while extracted
parasitics, field solutions and conducted/radiated measurements establish
different facts. A lumped Buck/Boost waveform without parasitics cannot
establish EMC compliance, switching-node overshoot or an acceptable board layout.
