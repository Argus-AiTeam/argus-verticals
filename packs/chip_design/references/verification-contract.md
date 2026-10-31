## Existing accelerator verification records

Existing accelerator verification keeps this source-bound record format; do not
substitute the APB4 control adapter or invent physical results. This is not a
generic `CHECK`/`PASS regression` format and not a substitute for a project's
numerical evaluator. CPU-only scientific work keeps its native project workflow:
do not invent an RTL manifest to make that work fit here. The bounded control
profile has its own separate [contract](control-contract.md).

`verification/RESULTS.json` has these fields: a passing `status`, nonempty
`commands`, `coverage`, `scenarios`, `numerical`, `raw_artifacts`, and
`source_copies`. Each command needs its actual nonempty string `argv` and integer
`exit_code: 0`; compilation alone is not a numerical pass. Raw files must exist,
and contradictory failure evidence is rejected. JSON objects cannot repeat a
field, and numeric values must be finite; `NaN`, infinity and overflowing numeric
literals are not missing-data placeholders. The project also needs executable
verification source (`.v`, `.sv`, `.py` or `.sby`) under `tb/`, `testbench/`,
`verification/`, `formal/` or `reference/`.

`source_copies` maps each consumed source to an independent byte copy retained
when the run consumed it:

```json
{
  "source_copies": {
    "reference/oracle.py": "snapshots/verification/reference/oracle.py",
    "design/numerical-contract.json": "snapshots/verification/design/numerical-contract.json"
  }
}
```

This excerpt is not a complete result. The RTL manifest and all its declared RTL
and generated sources remain mandatory. Every additional declared binding is
checked too, not just those mandatory RTL paths: each source must still equal
its copy byte for byte, and a copy must be a separate file. Missing, external,
stale or malformed declared files cannot be silently ignored. Keep copies
outside `tb/`, `testbench/`, `verification/`, `formal/` and `reference/`, so a
copied RTL file is not mistaken for verification source.

For project-owned numerical dependencies, an optional `verification/PLAN.json`
can require a set of supporting files:

```json
{
  "supporting_files": [
    "design/numerical-contract.json",
    "reference/oracle.py",
    "reference/rounding.py",
    "verification/fixtures/input.hex"
  ]
}
```

When the JSON plan exists, bind that plan in `source_copies`; every explicitly
declared supporting file must also be bound. If the field is present, the list
must be nonempty, distinct and project-relative. Other project-specific plan
fields do not replace these requirements. Projects without a JSON plan need none.

Declare the actual consumed contract, selected implementation/parameters,
evaluator helpers and small retained fixtures. This check does not discover
transitive imports or replace native checks of large model packages. Do not
rewrite old bindings or copies to make stale observations look current.
PPA, prototype and benchmark records also check all their declared source
bindings; final chip completion rechecks the referenced verification result.
Run `python3 '<this folder>/evidence.py' verification --project-root .` with the
workflow profile of the work; a `custom` scope also checks the RTL manifest.

## Accelerator precision and claim boundaries

Preserve the project's original numerical contract and independent evaluator
rather than replacing them with generic PASS criteria. Record weight/activation,
accumulator, residual and K/V formats separately; an FP16 operator boundary does
not imply all internal state is FP16. Keep packing order, signedness, group size,
scales/zero points, reduction order, rounding points/modes, overflow, saturation,
subnormal and invalid-value rules. Rounding once after the full reduction is not
equivalent to summing rounded group outputs. Do not substitute a CPU
floating-point reduction for an exact integer or RTL computation merely because
final text looks plausible.

Use directed cancellation, halfway/tie, group-boundary and extreme-value cases
with the project's specified bit/ULP/tolerance and independent reference. Bind
the original contract, oracle dependencies and retained input fixtures to the
run through `source_copies`. Preserve native project checks of large model
packages; do not duplicate all weights just to fill a generic form. Never use
expected outputs to select candidate bits, clamps or rounding modes.

Distinguish implementation tests, CPU numerical experiments, RTL simulation,
physical implementation and measured hardware. A repaired wrapper is not a
successful numerical hypothesis; a rejection remains a rejection. A task
that failed before a claim or numerical invocation is unmeasured, not a
numerically rejected experiment. Passing record checks cannot promote any
of these boundaries or relax the selected stage's original acceptance.

## Preserve the exact numerical variant

Match the original operator and selected parameter mode, not a generic label
such as FP16, INT4 or G128. A group primitive may round and saturate its output
while the full projection consumes its exact accumulator instead. Bias may be
added before one final rounding or after a separately rounded dot. Modes can
differ on signed underflow zero, exact cancellation, finite saturation, infinity
and invalid-input rejection. Never copy one mode's policy into another or use
an earlier milestone's contract to accept a later candidate.

Keep independent arithmetic correctness separate from the project's scientific
criteria: unchanged candidate output, failed downstream checks or failed paired
reference directions cannot become scientific success just because unit
comparisons passed. References are comparators, not inputs for selecting output
bits, clamps or tolerances. Preserve the original evaluator and native review.
Current file bindings alone do not prove execution, oracle independence,
adequate coverage, real entry compatibility or a supported scientific hypothesis.

## Checks and independent review

The Engineer runs the stage check in the execution project before asking for
review and gives its output with the decisive raw files. The Reviewer reruns it
when its tools include a shell; otherwise it inspects the original requirements,
source, oracle, raw observations and that recorded output with its read and
search tools, and never claims a run it did not make. A missing or failing
check is incomplete. Do not open a separate validation-only task or repeat
Engineer runs to stand in for review.

An empty issue list is not Reviewer approval or proof of physical qualification:
the check reads records; it does not replay recorded commands, run an arbitrary
project evaluator, program a board or energize hardware. Where the original
task explicitly asks for a diagnosis, the task can finish with failed
engineering requirements; report those failures, original limits and model
boundaries. Design and repair must meet the original conditions. Do not raise a
limit after observing a failure. Preserve failed attempts and keep incomplete
execution distinct from a valid negative result. Missing tools or exhausted
execution budgets are not a pass.

## Continuation without consuming old work

Inspect the current native task, runtime identity, retained inputs and review
before applying a saved continuation note. A repository snapshot is not live state.
Do not replace an old runtime with the ambient checkout, clear historical
claims, revive failed attempts or reuse consumed output namespaces.

Before an authorized new scientific run, validate the real entry contract,
dependency list and fresh-process import order with explicitly no-claim,
non-scientific fixtures. New scientific execution needs the operator's go-ahead
through the Manager; the Engineer cannot settle an ownership question by editing
task state. Preserve timeouts, interruptions and failed attempts. Missing
in-memory K/V state is not restored by a source checkout or an unrelated disk
checkpoint.
