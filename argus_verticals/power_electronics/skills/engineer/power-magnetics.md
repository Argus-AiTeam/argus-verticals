---
name: Magnetics and Inductor Behavior
description: "Volt-second balance, ripple, flux, saturation, winding and core loss."
---

# Separate electrical inductance from a magnetic component

For a linear inductor, di/dt=v/L and stored energy is L*i^2/2.
Integrate each switching interval's actual terminal voltage, including
winding loss, rather than inserting an ideal voltage ratio without checking
conduction mode. RMS current controls copper heating; peak current and bias
affect saturation margin.

Flux change follows the winding volt-seconds divided by turns and effective
core area. Reset imbalance can accumulate even if a short transient looks
acceptable. Differential inductance can fall with bias and temperature.

Core-loss fits depend on material, flux waveform, frequency, temperature and
the validity of the fitted method. Skin/proximity effects change winding loss.
A fixed L plus DC resistance represents none of these nonlinear or AC effects.
Do not infer a physical core, winding or saturation rating from that model.
