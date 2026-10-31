---
name: Package Substrates and Redistribution
description: "Connect layer geometry, escape routing and process rules to the actual package interface."
---

# A package substrate is a process-specific interconnect

Specify layer order, conductor/dielectric dimensions, via structures, pitch,
alignment tolerances and connection interfaces. Organic, ceramic and silicon
interconnect technologies are not interchangeable design-rule sets.
Redistribution layers need traceable line/space and via rules.

Check that die-side connections can escape to package-side terminals while
preserving net identity and return continuity. Reference discontinuities,
via transitions, power/ground assignment and routing density can dominate
signal quality. A connectivity count alone does not establish routability.

Keep mask/process layers distinct from electrical nets and physical materials.
Manufacturer rules, stackup data and assembly constraints are required before
claiming manufacturability. A board-level KiCad check is not a substitute for
package-substrate rule verification.

The initial thermal model treats each rectangular layer as a homogeneous
isotropic solid. A substrate with patterned copper, vias or strong anisotropy
needs justified homogenization or a different model; an arbitrary conductivity
value must not conceal that approximation.
