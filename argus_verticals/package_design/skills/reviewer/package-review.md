---
name: Package Independent Thermal Review
description: "Check original assumptions, native fields, heat balance and the limits of a numerical conclusion."
---

# Review the model as well as the output

Read the original request and canonical contract independently of the
Engineer's explanation. Confirm geometry, layer ordering, conductivity,
source distribution, boundary conditions and original thresholds are unchanged.
Read the host-executed checker result for the saved scope and actual project.
Reviewer is read/search-only; missing or failed host evidence is incomplete.
Do not claim shell execution or use an Engineer-authored Reviewer run instead.

Inspect real native logs, completed-step fields, conformal interface evidence
and heat balance. Where one-dimensional assumptions apply, independently
calculate t/(k A) and the expected temperature rise. For spreading, inspect
actual element counts and the declared mesh comparison rather than a nominal
mesh-size label alone.
For bottom-only convection, independently add 1/(h A); exclude internal
interfaces from the cooling area and include exposed ledges. Check both total
heat and native nodal film-load balance. Confirm that native NT is explicitly
identified as rise above ambient and reported Kelvin metrics include that
reference. A prescribed coefficient does not establish airflow or physical
cooling performance.

Separate a model's area-averaged source temperature from its maximum nodal
temperature and from a measured junction temperature. Do not call model
resistance standardized theta-JA/theta-JC without the corresponding definition.

Explain limitations and unresolved material/interface uncertainty. Reject
invented records, relaxed requirements, unsupported stress/reliability claims
or source edits beyond permission. A native replay confirms reproducibility,
not physical truth of the assumed model.
