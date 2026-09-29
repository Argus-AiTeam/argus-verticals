---
name: Passives and Physical Sensitivity
description: "Identify parasitic, leakage, loading and coupling mechanisms that ideal lumped circuit models omit, without claiming physical-layout execution."
---

# Know which nonidealities can change the decision

A resistor may need tolerance, temperature coefficient, voltage coefficient,
noise, power rating and package parasitics. A capacitor can have ESR, ESL,
leakage, dielectric absorption and capacitance that changes with voltage or
temperature. An inductor can require winding resistance, core loss, saturation
and self-resonance. Select the mechanisms appropriate to the operating range;
do not add arbitrary parasitics solely to make a curve look realistic.

Include source impedance, probe/load capacitance and finite output resistance
when they matter. Ground/reference impedance can turn return currents into
signal error. High-impedance nodes can be dominated by leakage and contamination;
small thermal gradients can matter in precision measurements. Coupling paths
depend on geometry and return paths, which a simple schematic may not represent.
Separate conducted disturbance, capacitive/inductive coupling and radiation.

Translate physical concerns into bounded sensitivity calculations where a
lumped approximation is justified. State where that approximation fails:
distributed transmission lines, package resonances and electromagnetic fields
can require a different solver and measured/extracted models. A simulated
parasitic capacitor is not evidence that a board has that capacitance.

This domain does not execute PCB placement/routing, package extraction, thermal
qualification, RF electromagnetic analysis or laboratory measurements. Preserve
such exclusions explicitly and hand the appropriate question to its independent
domain when available. Do not energize equipment or infer permission from a
simulation task. The model-level answer should identify which missing physical
information could materially change the result, rather than implying board
readiness from a clean ideal-circuit calculation.
