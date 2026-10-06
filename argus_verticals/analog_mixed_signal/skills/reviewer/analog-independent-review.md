---
name: Independent Analog Evidence Review
description: "Review actual circuit/model assumptions, native numerical evidence and scoped claims, rather than accepting only a report or solver exit code."
---

# Review the circuit and the experiment

Read the original requirements, circuit files and model descriptions before
the final summary. Check reference directions, units, bias, loading, input/output
ranges and the physical meaning of the excitation. Confirm that every named
condition corresponds to the actual deck, not merely its filename. A model
that omits saturation or noise cannot establish those aspects of performance.

Read the host-executed stage checker result for the saved scope and actual
execution project. Reviewer is read/search-only; do not claim shell execution.
Missing or failed host evidence is incomplete, not a request to impersonate
Reviewer through another Engineer run. Inspect native ngspice output and the
exact commands as well. Passing copies
and numeric bounds establish consistency, not genuine execution or adequate
physics. Verify the comparison is independent and the declared tolerance is
justified. Look for post-hoc bounds, stale waveforms, relaxed solver settings
and unsupported methods disguised as another kind of result.

Check interpolation and resolution around extrema or crossings. Finite samples
may miss narrow features; multiple crossings can invalidate a one-number
interpretation. Distinguish a closed-loop response from a properly measured
return ratio, and a sampled tail from a full settling guarantee. Inspect
convergence warnings in context rather than treating all warnings as either
automatic failure or automatic permission to ignore numerical problems.

Approve only the selected scope. Require a clear statement of ideal/behavioral
assumptions, omitted mechanisms and any need for measured or extracted data.
If records are missing or numerical reliability fails, request a concrete
repair or report the missing capability. Preserve valid out-of-limit findings
for a fixed diagnosis rather than demanding an unrequested redesign. Never create successful
measurements or modify completion state to compensate for an incomplete study.

For an operating envelope, independently verify the full original combination
set, generated parameter values, coarse/fine controls and all failed conditions.
Distinguish an accepted negative diagnosis from a passing circuit. Inspect the
worst headroom and actual parameter coordinates, not just the nominal plot.
Check that combined worst values come from both coarse and fine runs and that
the report names the selected resolution. Do not confuse positive distance to
a bound with satisfying its required margin; compare `*_margin_surplus` too.
When numerical evidence is unchanged, reuse its accepted comparison and focus
report corrections on interpretation rather than another solver run.
