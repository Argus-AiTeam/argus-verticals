---
name: Hardware Evidence Review
description: "Treat a passing record check as consistency only; keep numerical, RTL, implementation and measured-hardware claims apart."
---

# A passing check is not approval

`evidence.py` checks one stage's records. Inspect the original requirements,
source, oracle, raw observations and the check's current output for the
claimed scope. Missing or failing check output is incomplete work. An
Engineer-authored file labeling a run as Reviewer execution is not a substitute.

Exit 0 is not Reviewer approval or proof of physical qualification. It
establishes record consistency, not oracle independence, log authenticity,
sufficient coverage or that the logs came from the named tools. This pack has
no diagnosis mode: design and repair must meet the original conditions. Report
failures, original limits and model boundaries; do not raise a limit after
observing a failure.

A record check does not replay recorded commands, run a project evaluator,
program a board or energize hardware. Preserve failed attempts and keep
incomplete execution distinct from a valid negative result. Missing tools or
exhausted execution budgets are not a pass. Do not mutate the operator's RTL to
test an oracle without permission; use a private copy if a mutation check is
needed.

## Accelerator precision and claim boundaries

For accelerator work, preserve the project's original numerical contract and
independent evaluator rather than replacing them with generic PASS criteria.
Record weight/activation, accumulator, residual and K/V formats separately;
an FP16 operator boundary does not imply all internal state is FP16. Keep
packing order, signedness, group size, scales/zero points, reduction order,
rounding points/modes, overflow, saturation, subnormal and invalid-value rules.
Rounding once after the full reduction is not equivalent to summing rounded
group outputs. Do not substitute a CPU floating-point reduction for an exact
integer or RTL computation merely because final text looks plausible.

Use directed cancellation, halfway/tie, group-boundary and extreme-value cases
with the project's specified bit/ULP/tolerance and independent reference. Bind
the original contract, oracle dependencies and retained input fixtures to the
run by listing them in `supporting_files` of `verification/PLAN.json` (see
[records.md](../../records.md)). Preserve native project checks of large model
packages; do not duplicate all weights just to fill a generic form. Never use
expected outputs to select candidate bits, clamps or rounding modes.

Distinguish implementation tests, CPU numerical experiments, RTL simulation,
physical implementation and measured hardware. A repaired wrapper is not a
successful numerical hypothesis; a rejection remains a rejection. A task
that failed before a numerical invocation is unmeasured, not a numerically
rejected experiment. Passing record checks cannot promote any of these
boundaries or relax the selected stage's original acceptance.
