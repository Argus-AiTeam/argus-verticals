---
name: Native Package Thermal Execution
description: "Use the canonical contract, genuine Gmsh/CalculiX commands and preserved current evidence."
---

# Use actual geometry, mesh and fields

The role prompt supplies the authoritative `package/PLAN.json` and model schema,
Store-safe execution and read-only checking commands. Preserve the user's
model and original numerical conditions. A successful process exit is not
enough: actual mesh and solution files must agree with the requested physics.

Gmsh creates a conformal mesh through native Boolean fragments and physical
groups. Validate layer volumes, shared interfaces and top/bottom areas rather
than trusting labels. CalculiX consumes C3D4 elements, conductivity, temperature
DOF 11 constraints and consistently integrated nodal heat loads.

Read NT and RFL at the completed steady step. In fixed-bottom mode only,
bottom-node RFL represents extracted heat. In convection mode NT is rise above
the explicitly recorded ambient reference, and RFL includes net film extraction.
Use exterior face integrals for bottom heat, not bottom-node sums that can
include other surfaces. Check conservation against the original positive
power; do not adjust power to fit the result.

The checker re-executes both native tools in a temporary directory. Failed
attempts remain intact, existing results are never silently overwritten, and
native version changes require a new run. Unavailable tools or unsupported
physics must be explicit failures, not substituted scalar equations.
