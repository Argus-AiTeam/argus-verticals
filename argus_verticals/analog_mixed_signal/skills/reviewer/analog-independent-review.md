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

Run the supplied read-only stage checker from the execution project directory.
Inspect native ngspice output and the exact commands as well. Passing copies
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
If records are missing or a relevant numerical condition fails, request a
concrete repair or report the missing capability. Never create successful
measurements or modify completion state to compensate for an incomplete study.
