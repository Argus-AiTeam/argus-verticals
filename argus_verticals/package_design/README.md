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

## Executable first version

Gmsh creates conformal 3D linear-tetrahedral meshes of original, centred
rectangular package layers. CalculiX performs steady heat conduction with
constant isotropic conductivity, perfect bonding, a fixed-temperature bottom,
uniform top-face total power and otherwise adiabatic exposed surfaces.
Different-width layers model actual die/substrate spreading; those studies
require a declared coarse/fine comparison.

Native fields, material volumes, shared interfaces, boundary areas, total power
and heat balance are checked. A separate temporary native replay verifies the
saved results without changing the project. This is not a homemade solver or a
PASS-shaped JSON substitute.

```bash
# Ubuntu 24.04 native tools:
sudo apt-get install gmsh calculix-ccx
pip install 'argus-verticals[package]'
python -m argus_verticals.package_design.run_reference /tmp/package-reference
python -m argus_verticals.package_design.run_analysis /path/to/prepared-project
```

Gmsh 4.12.1 / CalculiX 2.21 are the initial validated versions. The reference
runs four real studies: a slab with independent R=t/(kA)=1 K/W, a two-layer
stack with R=sum(t/(kA))=1.5 K/W, and coarse/fine meshes of a smaller die on a
larger substrate. The last pair checks declared numerical agreement, not a
rigorous discretization-error bound.

No arbitrary CAD, contact/voids, transient, convection/radiation, CFD, electrical
parasitics, stress/warpage/fatigue or physical package qualification is claimed.
Thermal conductivity values need traceable material sources; package labels
are not material data. Model thermal resistance is not automatically a JEDEC
theta-JA or theta-JC measurement.

## Sources

- [Gmsh reference manual](https://gmsh.info/doc/texinfo/gmsh.html): OpenCASCADE fragments, physical groups and native MSH 2.2.
- [CalculiX official documentation](https://www.dhondt.de/): `*HEAT TRANSFER,STEADY STATE`, conductivity, DOF 11 boundary/load and NT/RFL output.
- [CalculiX 2.21 manual](https://www.dhondt.de/ccx_2.21.pdf): installed-version input and field semantics.

All reference geometry, models and scripts are original. Upstream tools and
documentation retain their own licenses and are not bundled into Store archives.
