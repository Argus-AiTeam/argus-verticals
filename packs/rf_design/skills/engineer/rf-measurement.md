---
name: VNA Measurements and Reference Planes
description: "Preserve measurement provenance, port maps and calibration assumptions; distinguish wave renormalization from fixture removal or measured evidence."
---

# Identify what the file represents

Record the source, physical device, port map, reference planes, frequency grid,
bias, excitation level and calibration conditions. A file extension does not
prove a VNA measurement. Generated analytic data must remain explicitly
synthetic. Keep the original file unchanged and retain exact execution copies.

Calibration removes modeled systematic measurement errors at its defined
planes; fixtures and adapters beyond those planes can remain in the result.
Connector repeatability, cable motion, drift, dynamic range and receiver noise
contribute uncertainty. SOLT and TRL have different standards and assumptions.
This adapter does not execute either calibration or certify its quality.

Renormalizing a 50-ohm file to 75 ohms changes the wave reference, not the
measurement plane, device bias or fixture. De-embedding requires a justified
fixture model and orientation, can amplify noise, and is outside this first
executable scope. Swapping ports is not de-embedding or inversion.

Touchstone options specify units, parameter type, representation and reference
impedance. Confirm whether data are single-ended or mixed-mode and whether
noise information is present. The reader deliberately rejects unsupported
conventions instead of silently stripping them. Monotonic finite samples and
plausible S values are necessary consistency checks, not proof of calibration.
Compare against physically justified expectations and state the remaining
uncertainty in the conclusion.
