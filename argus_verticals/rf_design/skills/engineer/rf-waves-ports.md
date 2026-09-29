---
name: RF Waves, Ports and Reference Impedances
description: "Use correct S-parameter indexing, power-wave normalization and dB conventions, and distinguish reference changes from physical circuit changes."
---

# Define the wave convention before interpreting a number

For positive real reference impedance R, normalized incident and reflected
waves satisfy a=(V+R*I)/(2*sqrt(R)) and b=(V-R*I)/(2*sqrt(R)), with consistent
voltage/current phasor conventions. The S matrix maps b=S*a. S21 means response
at port 2 from incidence at port 1; scikit-rf arrays use `[frequency,1,0]`,
while this provider's plan uses human-readable ports `[2,1]`.

S parameters are dimensionless. Use 20*log10(abs(Sij)) for magnitude in dB,
not 10*log10(abs(Sij)). Positive return loss is -20*log10(abs(S11)).
Do not confuse dB ratios with absolute dBm power, or RMS voltage with peak
voltage. With other ports matched to the stated references, abs(S21)^2 describes
normalized transmitted power. Arbitrary mismatched source/load transducer gain
requires more information; it is not automatically that same number.

Renormalization changes reference waves, not the device, its physical load,
calibration or reference-plane location. Port permutation changes indexing,
not network inversion. Preserve labels and explicitly trace both axes of S.
Complex-reference definitions differ between power, pseudo and traveling waves;
the first adapter rejects such references rather than guessing their meaning.
Use explicit reference values from the source file, not an assumed universal
50 ohms. An exact ideal zero reflection needs a magnitude comparison because
its logarithm is not finite.
