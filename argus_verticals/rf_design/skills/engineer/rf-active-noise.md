---
name: Active RF, Noise and Linearity
description: "Separate small-signal gain from noise, compression and frequency conversion; use noise budgets only under explicit assumptions."
---

# A small-signal network is not a nonlinear radio model

LNA, mixer, oscillator and power-amplifier requirements are different.
S parameters at a stated bias can describe local linear gain and matching.
They do not establish compression, intermodulation, harmonics, efficiency,
oscillator startup or large-signal load-pull behavior. Record bias, power level,
temperature and whether the source data are measured or simulated.

For a cascade under the relevant matching assumptions, Friis' noise-factor
relation is Ftotal=F1+(F2-1)/G1+(F3-1)/(G1*G2)+..., using linear noise factors
and power gains. Converting noise figure or gain in dB directly into that sum
is incorrect. Loss ahead of an LNA, mismatch and source noise conditions can
matter substantially. Thermal-noise density and integrated noise require
temperature and effective bandwidth.

IP3, P1dB, noise figure and gain are not interchangeable. Mixer conversion
gain/loss depends on LO drive, sideband conventions, frequency plan and ports;
a same-frequency two-port S matrix does not replace a conversion model.
Oscillator phase noise and startup require suitable nonlinear/dynamic methods.

These topics are knowledge coverage. The first executable adapter rejects
Touchstone noise blocks and does not calculate nonlinear or mixer performance.
Do not relabel a small-signal transmission check as noise or power-amplifier
qualification. A powered active network can legitimately have singular value
above one; passivity is not the right acceptance condition for its gain.
