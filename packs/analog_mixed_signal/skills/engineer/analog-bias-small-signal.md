---
name: Analog Bias and Small-Signal Foundations
description: "Establish operating regions, loading, units and incremental models before interpreting DC or AC circuit results."
---

# Establish the operating point

Define reference ground, source polarity and current direction first. Ngspice
reports a voltage-source branch current in its defined reference direction;
a negative supply-source current can mean delivered power, not an error.
Check Kirchhoff consistency and expected voltage/current magnitudes. Floating
nodes, missing DC return paths and ideal-source contradictions are modeling
problems, not reasons to accept arbitrary convergence settings.

For a divider, include load resistance explicitly:
Vout = Vin * (Rbottom || Rload) / (Rtop + (Rbottom || Rload)).
The unloaded formula is not a valid independent comparator when the output
is loaded. Capacitors are open and inductors short in the ideal DC limit,
but real leakage and winding resistance can determine the physical bias.

Linearize devices around the established operating point. For a long-channel
MOS approximation in its stated regime, gm approximately equals 2*Id/Vov;
for an ideal bipolar device, gm approximately equals Ic/Vt. These are useful
checks, not substitutes for a modern device model outside their assumptions.
Check common-mode range, output headroom, body connections and operating region.

AC analysis is an infinitesimal perturbation of that bias. Its source amplitude
is a normalization, not a large-signal swing that demonstrates absence of
clipping. A circuit can have excellent small-signal gain around an impossible
or unwanted bias. Use DC sweeps to explore static transfer and separate transient
experiments for recovery and amplitude-dependent effects. Record supply, load
and temperature assumptions with the model before comparing results.
