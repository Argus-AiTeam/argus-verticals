---
name: RF Study Planning
description: "Plan the minimum informative RF network graph, with explicit conventions and independent acceptance conditions."
---

# Design the comparison before the calculation

List the observable requirements, their units, ports, reference planes and
frequency positions/windows. Translate them into predeclared checks. An
insertion-loss question, a reflection question and a full-matrix passivity
question are different comparisons; one cannot substitute for the others.

Inspect source provenance and operating conditions. Choose only the required
network dependencies: source files, ideal sections, reference changes, port
reordering and cascade order. Require identical sampled grids before cascading
and explain explicit renormalization where port references differ. Do not
invent calibration or de-embedding data.

Use independent circuit equations or trusted reference data for the expected
values. Assess whether sampling resolves the physical features of interest.
If the required result needs complex references, mixed mode, nonlinear behavior,
noise parameters or EM fields, state the missing capability rather than forcing
it into the existing metrics.

Keep the same acceptance conditions for Engineer and Reviewer. Setup of the
canonical plan can occur within analysis scope. Reuse current valid evidence
when appropriate; otherwise preserve prior outputs before a justified repair
and rerun. A successful network study should produce its bounded conclusion,
not launch unrelated stages simply because they exist in the domain.
