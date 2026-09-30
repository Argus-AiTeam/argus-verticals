# Package design

Independent `hardware / package_design` domain. Broad knowledge covers package
selection, die attach, wire bond, flip chip, bumps, substrates, interposers,
chiplets, thermal paths, mechanical risks, assembly and test. It does not inherit
digital, analog, RF or PCB workflows. `vertical.json` declares Store identity,
numpy and shared hardware record utilities.

Profiles are `specification`, `model`, `thermal`, `review` and optional `full`.
Thermal-only analysis of a supplied model is valid. Review adds current thermal
evidence, not unrelated physical-design or manufacturing stages. The
[canonical contract](evidence-contract.md) is included in real role prompts.

## Executable thermal studies

Gmsh creates conformal 3D linear-tetrahedral meshes of original, centred
rectangular package layers. CalculiX performs steady heat conduction with
constant isotropic conductivity, perfect bonding and uniform top-face total
power. Choose either a fixed-temperature bottom or explicit convection to a
common ambient on selected exterior surfaces; remaining surfaces are adiabatic.
Different-width layers model actual die/substrate spreading; those studies
require a declared coarse/fine comparison.
All convection studies also require that comparison, preserving the original
ambient, film coefficient and surface selection.

Native fields, material volumes, shared interfaces, boundary areas, total power
and heat balance are checked. A separate temporary native replay verifies the
saved results without changing the project. This is not a homemade solver or a
PASS-shaped JSON substitute.

```bash
# Ubuntu 24.04 native tools:
sudo apt-get install gmsh calculix-ccx
pip install 'argus-verticals[package]'
python -m argus_verticals.package_design.run_reference /tmp/package-reference
python -m argus_verticals.package_design.run_convection_reference /tmp/package-convection-reference
python -m argus_verticals.package_design.run_analysis /path/to/prepared-project
```

Gmsh 4.12.1 / CalculiX 2.21 are the initial validated versions. The reference
runs four real studies: a slab with independent R=t/(kA)=1 K/W, a two-layer
stack with R=sum(t/(kA))=1.5 K/W, and coarse/fine meshes of a smaller die on a
larger substrate. The last pair checks declared numerical agreement, not a
rigorous discretization-error bound.

The convection reference adds six studies: coarse/fine bottom-cooled slab
R=t/(kA)+1/(hA)=11 K/W, top-cooled uniform-temperature solid R=1/(hA)=10 K/W,
and a stepped die/substrate with all exposed surfaces cooled. Native film faces
exclude bonded interfaces and include exposed ledges. The checker integrates
face heat and checks nodal RFL with CalculiX C3D4's centroid film quadrature,
including nodes shared by heated and cooled surfaces.

For this linear model with one common ambient, convection solves temperature
**rise** natively and explicitly records `temperature_reference_k`. Physical
Kelvin metrics add the ambient back; resistance uses the rise directly to
preserve small signals. Raw DAT/FRD NT is therefore not absolute temperature.
The legacy fixed-bottom mode still solves absolute temperature.

No arbitrary CAD, contact/voids, transient, radiation, CFD, electrical
parasitics, stress/warpage/fatigue or physical package qualification is claimed.
Convection coefficients are prescribed, traceable inputs, not airflow predictions.
Mixed fixed-temperature/convection boundaries, different ambients and
temperature-dependent film coefficients are not implemented.
Thermal conductivity values need traceable material sources; package labels
are not material data. Model thermal resistance is not automatically a JEDEC
theta-JA or theta-JC measurement.

## Sources

- [Gmsh reference manual](https://gmsh.info/doc/texinfo/gmsh.html): OpenCASCADE fragments, physical groups and native MSH 2.2.
- [CalculiX official documentation](https://www.dhondt.de/): `*HEAT TRANSFER,STEADY STATE`, conductivity, DOF 11 boundary/load and NT/RFL output.
- [CalculiX 2.21 manual](https://www.dhondt.de/ccx_2.21.pdf): installed-version input and field semantics.
- [CalculiX thermal element implementation](https://github.com/Dhondtguido/CalculiX/blob/078778112369f18a207de039d50307d5797f941b/src/e_c3d_th.f): C3D4 uses one triangular-face integration point; native 2.21 regressions check the resulting RFL convention.

All reference geometry, models and scripts are original. Upstream tools and
documentation retain their own licenses and are not bundled into Store archives.
