---
name: PCB Power Distribution and Thermal Reasoning
description: "Bound board-level current, resistance, decoupling and heat-path assumptions without claiming a field solution."
---

# Model the actual current loop

Separate average, peak and transient current. For a uniform conductor,
R = rho L / A and P = I_rms² R give first-order loss estimates; copper thickness,
temperature dependence, vias, connectors and spreading resistance matter.
These equations do not determine an allowed temperature rise by themselves.

Decoupling effectiveness depends on loop inductance, placement, supply/return
transitions, capacitor bias derating and frequency-dependent impedance.
Capacitance totals alone do not establish transient response. Distinguish bulk
energy storage from local high-frequency return paths.

Thermal resistance depends on package, copper, board stackup, airflow and
boundary conditions. Datasheet theta values measured on a specified test board
are not universally transferable. Identify heat sources, dissipation estimates,
conductive paths and temperature-sensitive neighbors.

Do not claim current-carrying capability, junction temperature or stable
converter operation from ERC/DRC. Use a properly bounded electrical/thermal
model or measurement when required, and state what the current board evidence
does not resolve.
