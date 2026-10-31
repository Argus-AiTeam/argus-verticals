---
name: RF Passivity, Reciprocity and Stability
description: "Use a full-matrix passivity criterion, state reciprocity conventions, and keep active stability separate from passive sampled-network checks."
---

# Check the claim actually being made

For the supported positive-real power-wave references, passive behavior at a
frequency requires I-S^H*S to be positive semidefinite, equivalently the
largest singular value of S is at most one. Checking each column's power
sum alone is insufficient: correlated multiport excitations can reveal gain
even when every individual column norm is below one. Use a justified
numerical/measurement tolerance, not an arbitrary large allowance.

Reciprocity means the correctly normalized S matrix is symmetric under the
supported conventions. It is not a statement that forward and reverse phase
are irrelevant, that every device is passive, or that ports can be swapped
without recording the mapping. Losslessness, reciprocity and matching are
different properties.

An active two-port's stability depends on source/load terminations and
frequency coverage. Rollet K and the determinant condition are useful under
their stated small-signal two-port assumptions, but do not establish nonlinear
startup behavior, multi-loop stability or operation outside the measured band.
This first adapter does not provide an automatic active-stability verdict.

Finite sampled passivity is not global passivity or causality. Sparse data can
miss narrow violations; interpolation, extrapolation and fitting may introduce
new problems. The checker reports bounded numerical facts rather than claiming
that a physical system is safe, unconditionally stable or causal everywhere.
