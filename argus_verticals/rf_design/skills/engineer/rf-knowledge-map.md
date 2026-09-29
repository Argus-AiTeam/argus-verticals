---
name: RF Network Knowledge Map
description: "Navigate RF questions by observables, reference planes and physical assumptions; choose only the necessary network study."
---

# Start with the requested RF observable

Define frequency, power/bias regime, physical ports, reference planes, source/load
conditions and numerical tolerances. A small-signal S-parameter file is not a
complete description of noise, compression, intermodulation, oscillation or
radiation. Decide what the available data can actually establish.

- [Waves and port conventions](rf-waves-ports.md): units, indexing, normalization and power interpretation.
- [Transmission lines](rf-transmission-lines.md): characteristic impedance, delay, loss and distributed limits.
- [Impedance matching](rf-matching.md): Smith-chart reasoning, L networks and bandwidth tradeoffs.
- [Filters and resonators](rf-filters.md): loaded Q, insertion/return loss and sampling.
- [Active RF, noise and linearity](rf-active-noise.md): gain budgets, noise figures and nonlinear limits.
- [Stability and physical constraints](rf-stability-passivity.md): full-matrix passivity, reciprocity and active stability.
- [Measurement and reference planes](rf-measurement.md): VNA calibration, fixtures, uncertainty and provenance.
- [RF physical realization](rf-physical.md): interconnects, packaging, antennas, coupling and missing EM models.
- [Reproducible network studies](rf-network-execution.md): the supported scikit-rf calculations and evidence.

This first executable adapter covers linear single-ended networks with positive
real, frequency-independent port references. Broader topics provide engineering
reasoning, not an automatic solver for every method discussed. Explicitly
identify when a task needs calibration, mixed-mode conversion, nonlinear device
models, full-wave fields or physical measurements that this adapter cannot supply.
