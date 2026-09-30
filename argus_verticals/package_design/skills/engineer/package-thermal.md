---
name: Package Thermal Modeling
description: "Define the heat source, cooling boundary, material model and numerical uncertainty before interpreting temperatures."
---

# Boundary conditions define the thermal question

Specify total power, its spatial distribution, the cooling boundary and all
other exposed-surface conditions. Uniform top-face power is not the same as
volumetric die dissipation or a localized hotspot. A prescribed bottom
temperature is not ambient air temperature with an unspecified heat sink.

For an equal-area, perfectly bonded stack with uniform top flux and adiabatic
sides, R = sum(t_i/(k_i A)) and T_top = T_bottom + P R are independent
one-dimensional checks. Different lateral dimensions produce three-dimensional
spreading, so the simple sum generally no longer gives the whole solution.
With bottom-only convection, add 1/(h A) to that series resistance and reference
the rise to the prescribed ambient. Top-only convection with uniform top heat
has uniform rise P/(h A) and no conduction gradient. Other exposed cooling
requires native field integration, not blindly adding a scalar resistance.

Choose fixed bottom or explicit convection, not both. Preserve ambient,
coefficient source and selected exterior groups between coarse and fine runs.
All convection studies need refinement; a coefficient is an input assumption,
not evidence that airflow was simulated.

Use consistent SI quantities: metres, W/(m K), watts and kelvin. Conductivity
does not determine heat capacity; a steady-state result says nothing about
transient warm-up. Temperature differences in K equal differences in Celsius,
but absolute temperatures must not be substituted without conversion.

Inspect heat balance, imposed boundary values, material interfaces and mesh
sensitivity. A two-mesh agreement is evidence for that comparison, not a
rigorous accuracy certificate. Model theta_top depends on the chosen boundaries
and is not automatically a standardized junction-to-ambient/case resistance.
