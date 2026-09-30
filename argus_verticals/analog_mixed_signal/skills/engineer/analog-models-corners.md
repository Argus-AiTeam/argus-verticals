---
name: Device Models, Variation and Numerical Accuracy
description: "Record model provenance and valid regimes, distinguish corners from yield, and avoid treating convergence tricks as physical validation."
---

# A model is a conditional statement

Identify whether each model is ideal, behavioral, device-level or merely a
testbench. Record its source, license/access limitations where relevant, operating
ranges, temperature assumptions and omitted mechanisms. A transistor model name
does not demonstrate a foundry-qualified process. Do not substitute generic
parameters for an unavailable PDK while retaining process-specific claims.

Vary parameters for a physical reason. Component tolerances, temperature
coefficients, supply variation, load range and process corners represent different
uncertainties. Independent extrema are not always physically possible together,
and correlations can matter. A small corner set does not establish statistical
yield. Monte Carlo conclusions require explicit distributions, correlations,
sample counts and estimator uncertainty; the first adapter does not automate
that statistical claim.

Check convergence diagnostics and conservation/limiting behavior. Artificial
leak resistors, initial conditions, source stepping, reduced tolerances or relaxed
accuracy can alter the answer. Explain and preserve any justified solver/model
adjustment rather than silently changing it after a failed bound. Compare an
appropriate second resolution or method when numerical error threatens the
decision. A successful process exit is insufficient.

For this adapter, use separate single-analysis decks for requested conditions.
All included files use project-root-relative paths and are named in the plan;
the runner freezes their bytes. External library selection, dynamically loaded
device code and file-driven stimuli are outside its first reproducible subset.
Changing model or testbench bytes invalidates old results, even if filenames and
human-readable condition labels stay the same.

For a supplied parameter study, use the operating-envelope format in the
canonical contract instead of manually copying nominal results into corner
rows. Preserve the complete combination set, one common design and original
model-validity ranges. Temperature must act through the actual declared native
device equations; a temperature label does not change an ideal resistor or
capacitor. OP checks solver-tolerance sensitivity, whereas AC/DC/transient also
need an actual denser grid or smaller time step. Name the limitation precisely.
