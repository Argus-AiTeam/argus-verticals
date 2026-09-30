---
name: Independent RF Network Review
description: "Review physical interpretation, port/reference consistency and actual exported networks instead of trusting a success flag."
---

# Independently check the meaning and the numbers

Read the original request, supplied network data and actual plan. Confirm
whether inputs are measured, simulated or analytic; inspect the reference
planes, port map, normalization, bias and frequency coverage. A syntactically
valid file does not prove an appropriate physical model or calibration.

Run the supplied read-only checker from the execution project. Inspect the
exported Touchstone files and actual execution record. Compare the result
against an independent equation or justified reference, not solely against
another invocation of the same algorithm. Reject changed bounds that were
chosen after seeing the answer.

For passive claims, inspect the full S matrix's singular-value bound, not
only individual port sums. Reciprocity needs correct port indexing and
normalization. Distinguish source/load power gain from S21 when terminations
are not matched. Verify that frequency resolution supports the claimed
comparisons and that exact ideal nulls are not concealed by logarithmic floors.

Approve only the selected scope and its explicit limits. Network consistency
does not establish global causality, active-device stability, noise, radiation,
layout, calibration quality or safe hardware operation. Request a concrete
repair when needed; never fabricate measurements or change completion state
to compensate for missing evidence.

For robustness, compare case coverage with the original Cartesian axes,
including nominal, and check both grids, common design, worst-frequency
witnesses and required headroom. Independently check selected complex S values
against circuit equations. A valid negative diagnosis may complete; a design
with any failed original limit or required margin may not. Missing/undefined
measurements and failed refinement invalidate either conclusion. Do not replace
an honest negative diagnosis with fabricated passing results.
