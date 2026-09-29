---
name: Noise and Dynamic Range Reasoning
description: "Build dimensionally correct noise budgets and distinguish theoretical estimates from unavailable native noise or distortion analysis."
---

# Keep spectral density distinct from integrated noise

For an ideal resistor at temperature T, the open-circuit voltage-noise density
is sqrt(4*k*T*R) V/sqrt(Hz). Integrate power spectral density through the relevant
transfer function and bandwidth before taking a square root. Multiplying a
density by bandwidth instead of its square root is dimensionally wrong.
Noise-equivalent bandwidth need not equal the -3 dB bandwidth.

Refer noise sources consistently to input or output. Include amplifier voltage
noise, current noise acting through frequency-dependent source impedance,
feedback-network noise and relevant reference/supply coupling. Sum powers for
uncorrelated sources, but do not assume independence where correlation matters.
Separate thermal, shot, flicker and sampled noise assumptions. The k*T/C estimate
is tied to a sampling/reset model and does not describe every capacitor's noise.

State whether amplitudes are RMS, peak or peak-to-peak, and whether spectra are
one-sided or two-sided. Dynamic range, SNR, SINAD, THD and SFDR are not synonyms.
Distortion requires an appropriate nonlinear model and a justified spectral
measurement; a linear AC response cannot establish it. Sampling, windowing,
record length and coherent excitation affect FFT interpretations.

This provider's initial native reader does not validate ngspice noise analyses,
distortion analyses or spectral-performance claims. Use the equations for a
clearly labeled estimate and identify missing device information. If the request
requires a genuine noise or distortion result, report the unsupported analysis
instead of presenting a transient plot or a hand-filled number as equivalent
evidence. Retain the numerical scope that was actually executed.
