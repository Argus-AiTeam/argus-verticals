---
name: Isolated and Resonant Conversion
description: "Flyback, forward, bridge and resonant conversion with explicit magnetic and isolation limits."
---

# Distinguish energy transfer mechanisms

A flyback stores energy in magnetizing inductance and releases it during the
other switching interval. A forward converter transfers energy during the
active interval and needs a defined core-reset mechanism. Turns ratio alone
does not settle either design's flux swing or device voltage stress.

For bridges, separate transformer magnetizing current from reflected load
current and account for leakage inductance, dead time and flux imbalance.
For LLC or other resonant stages, define operating frequency relative to the
resonances, load range and rectifier behavior before claiming soft switching.

Leakage-induced overshoot, winding capacitance, rectifier recovery and clamp
loss need applicable models or measurements. Creepage, clearance and insulation
qualification are physical requirements, not conclusions from an isolated
schematic symbol. The first native adapter does not execute these topologies.
