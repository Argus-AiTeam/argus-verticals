---
name: Power Semiconductors and Drivers
description: "MOSFET, IGBT, SiC/GaN, diode and drive assumptions, with conduction versus switching behavior."
---

# Bind the device model to its question

Distinguish a resistance-controlled switch from a transistor model with
nonlinear capacitances, charge, body-diode behavior and temperature dependence.
Ron-based dissipation cannot establish switching loss, avalanche capability,
reverse recovery or a safe operating area.

Use datasheet curves at relevant voltage, current, temperature and drive
conditions. MOSFET Rds(on), IGBT saturation behavior, diode forward drop and
SiC/GaN reverse conduction are not interchangeable idealizations.

Drive design must account for propagation mismatch, dead time, Miller
coupling, common-mode transient immunity and supply sequencing. A logic
waveform at the control node is not evidence of actual terminal drive.
Complementary-switch overlap and bootstrap limitations require dedicated
models and qualified physical evaluation; this adapter has neither.
