---
name: Nonisolated Converter Topologies
description: "Buck, Boost, buck-boost, conduction modes, voltage ratios and semiconductor stress."
---

# Establish topology assumptions

In ideal continuous conduction, Buck has Vout=D*Vin and Boost has
Vout=Vin/(1-D). These are averaged lossless relations, not complete switching
solutions. Include winding resistance, switch conduction and diode drop
before comparing a real model's operating point to those ideal ratios.

Use volt-second balance on the inductor and charge balance on the capacitor.
Check whether minimum inductor current stays positive; discontinuous conduction
changes the load-dependent conversion ratio. Light-load pulse skipping and
synchronous reverse current require different controller/device assumptions.

Inverting buck-boost, four-switch buck-boost, SEPIC and Cuk conversion have
different polarity, current paths and device stresses. A shared DC ratio does
not imply interchangeable current waveforms or component ratings.
Inspect startup and faults separately from periodic steady operation.
