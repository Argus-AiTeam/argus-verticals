---
name: Amplifiers and Operational Amplifiers
description: "Relate topology, input/output constraints, finite gain and large-signal behavior without overclaiming ideal op-amp models."
---

# Separate topology from device capability

Choose the amplifier topology from source impedance, required gain, bandwidth,
noise, output load and allowable input/output ranges. A non-inverting stage
has ideal gain 1+Rf/Rg, while an inverting stage has ideal gain -Rf/Rin and a
different source-loading/noise-gain problem. A transimpedance stage must include
sensor capacitance, feedback capacitance and stability requirements; substituting
a voltage amplifier with the same nominal gain misses its dominant constraints.

Finite open-loop gain produces closed-loop error. Input bias current through
source and feedback impedances creates offsets; offset voltage is amplified by
noise gain, which need not equal signal gain. Check input common-mode limits,
differential-input limits, output swing versus load, current capability and supply
requirements against the actual model or data source. An ideal controlled source
has none of those limits unless they are modeled explicitly.

Small-signal bandwidth and large-signal slew rate are not interchangeable.
For a sinusoid of amplitude Vpk and frequency f, the needed slope is 2*pi*f*Vpk.
A model that omits a slew constraint cannot establish distortion-free operation
at that slope. Check saturation and recovery separately when those behaviors
matter. Preserve the distinction between differential and single-ended signals,
especially around fully differential amplifiers and ADC drivers.

The bundled one-pole feedback reference checks finite-gain equations only.
It deliberately lacks rails, saturation, slew limiting and current limiting.
Use its numerical result to validate the analysis method, not to recommend a
commercial component or claim that a powered physical circuit meets its limits.
