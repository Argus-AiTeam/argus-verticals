---
name: Startup, Protection and Fault Assumptions
description: "Initial energy, inrush, soft start, UVLO/OVP/current limits and explicit unsupported faults."
---

# Initial conditions are part of the engineering requirement

Distinguish an initially empty output capacitor from a prebiased output or a
DC-initialized simulation. Specify source application, control enable and
load timing. Soft start is a control behavior, not an automatically smooth
output trace from a convenient initial condition.

Consider inrush, reverse current, short circuit, open load, sensor failure,
loss of drive supply and restart behavior as separate scenarios. UVLO, OVP,
overcurrent protection and latching/retry policies need explicit thresholds,
delays and applicable device limits.

The initial adapter starts with zero L current and C voltage, and has no
soft-start controller, current limiter or protection hardware. Its nominal
48 V/100 W execution bounds are not a physical safety certificate.
Keep physical operation outside the simulation task; do not infer permission
to energize equipment from a completed numerical study.
