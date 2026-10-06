## Existing accelerator verification records

This is the chip provider's existing RTL verification format, not the digital
verification specialty's `CHECK`/`PASS regression` format and not a substitute
for a project's numerical evaluator. CPU-only scientific work keeps its native
project workflow: do not invent an RTL manifest to make that work fit here.
The bounded control profile has its own separate contract.

`verification/RESULTS.json` retains its existing fields: a passing `status`,
nonempty `commands`, `coverage`, `scenarios`, `numerical`, `raw_artifacts`, and
`source_hashes`. Each command needs its actual nonempty string `argv` and integer
`exit_code: 0`; compilation alone is not a numerical pass. Raw files must exist,
and contradictory failure evidence is rejected. JSON objects cannot repeat a
field, and numeric values must be finite; `NaN`, infinity and overflowing numeric
literals are not missing-data placeholders.

`source_hashes` uses the existing SHA-256 object or list-of-objects format:

```json
{
  "source_hashes": [
    {"path": "reference/oracle.py", "sha256": "<actual digest at execution>"},
    {"path": "design/numerical-contract.json", "sha256": "<actual digest at execution>"}
  ]
}
```

This excerpt is not a complete result. The RTL manifest and all its declared RTL
and generated sources remain mandatory. Every additional declared binding is
checked too, not just those mandatory RTL paths. Each list entry must be a
complete object with a distinct nonempty path and a valid digest. Missing,
external, stale or malformed declared files cannot be silently ignored.

For project-owned numerical dependencies, an optional `verification/PLAN.json`
can require a set of supporting files, reusing the declaration spelling of the
digital verification specialty:

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

When the JSON plan exists, bind that plan in `source_hashes`; every explicitly
declared supporting file must also be bound. If the field is present, the list
must be nonempty, distinct and project-relative. Other project-specific plan
fields do not replace these requirements. No JSON plan is imposed on legacy
projects. The specialty continues using independent byte copies for its own
simulation/formal records; do not convert either provider's result format.

Declare the actual consumed contract, selected implementation/parameters,
evaluator helpers and small retained fixtures. This check does not discover
transitive imports or replace native checks of large model packages. Do not
rewrite old bindings or snapshots to make stale observations look current.
PPA, prototype and benchmark records also check all their declared source
bindings; final chip completion rechecks the referenced verification result.

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
