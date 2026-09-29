# Required verification records

All file paths below are relative to the execution project, remain inside it,
and identify nonempty files. Do not use absolute paths or `..` in record paths.
These are schema examples, not completed results. Substitute the operator's
actual sources, requirements, cases and complete configuration matrix.

## Plan manifest: required even for a simulation-only scope

`verification/PLAN.json` records the inputs and acceptance matrix:

```json
{
  "sources": ["rtl/stream_fifo.sv"],
  "testbenches": ["verification/tb_stream_fifo.sv"],
  "configurations": ["w8_d1_s1"],
  "cases": ["reset", "transfer", "stall"],
  "requirements": {
    "Reset discards outstanding transactions": ["reset"],
    "Accepted transactions preserve data and order": ["transfer"],
    "Output remains stable under backpressure": ["stall"]
  }
}
```

Each list contains distinct nonempty strings. Case IDs use lowercase letters,
digits and underscores, beginning with a letter. Every requirement maps to
known cases and every case is mapped to a requirement. Configuration names
identify parameters and seeds; retain the exact compile/run arguments so the
Reviewer can verify their correspondence.

A simulation-only scope omits the standalone plan stage, not this manifest.
Reuse an applicable existing plan. If absent, materialize the manifest from the
provided requirements while preparing the requested tests, without adding a
stage or expanding scope. Ask about genuinely unresolved requirements rather
than inventing them. Merely naming a nonexistent testbench is not a valid plan.

## Simulation: actual runs, independent input copies and comparison counters

`verification/RESULTS.json` has this structure:

```json
{
  "inputs": {
    "verification/PLAN.json": "verification/inputs/PLAN.json",
    "rtl/stream_fifo.sv": "verification/inputs/stream_fifo.sv",
    "verification/tb_stream_fifo.sv": "verification/inputs/tb_stream_fifo.sv"
  },
  "runs": [
    {
      "configuration": "w8_d1_s1",
      "command": ["vvp", "verification/build/w8_d1_s1.vvp", "+SEED=1"],
      "exit_code": 0,
      "log": "verification/logs/w8_d1_s1.log"
    }
  ]
}
```

`inputs` maps every plan/source/testbench file to an independent, byte-identical
copy. Include any extra inputs required by the consuming vertical. Self-copies,
hardlinks and paths escaping the project are invalid. Copy the inputs used for
the run; changes to the plan, RTL or testbench require rerunning affected checks
and updating the evidence, not merely copying changed files over old snapshots.

`runs` contains exactly one record per planned configuration, with no omissions,
duplicates or extras. `command` is the actual argv list, not a shell command
string. `exit_code` is the actual integer zero, not a boolean. Preserve
compilation commands/output too, for example as extra run fields or build logs.
Do not replace `inputs`/`runs` with a custom `configurations` report.

Instrument the independent scoreboard to emit, in each configuration's raw log:

```text
CHECK reset 3
CHECK transfer 200
CHECK stall 50
PASS regression
```

The numbers above illustrate the format only. Emit exactly one
`CHECK <case> <positive-count>` for **every** planned case and no other case IDs.
Counters must count actual successful comparisons, not elapsed cycles or
unconditional increments. Emit exactly the line `PASS regression` only after
the checks finish successfully. Preserve raw tool output; contradictory
`FATAL`, `ERROR` or `FAIL` markers reject the result. A normal exit, an aggregate
PASS line or a Markdown report is insufficient. Counts are not coverage closure.

## Formal: only when selected

The plan additionally declares `formal.mode` (`bmc` or `prove`), positive integer
`depth`, distinct nonempty `assertions` and `covers` lists, and an `assumptions`
list containing `expression` and `reason` for each assumption (explicit `[]` is
allowed). Include the property harness and SBY configuration in the plan inputs.

`verification/FORMAL.json` records `inputs` using the same copy rules, plus
`assertions` and `covers` objects keyed by exactly the declared property names.
Each entry records `mode`, `depth`, actual argv `command`, integer `exit_code`
and raw native SymbiYosys `log`. Assertion modes match the plan; cover entries
use `cover`. Depths match the plan. Each cover also names a nonempty `witness`.
Native output must contain `DONE (PASS, rc=0)` without a contradictory failed
result. A bounded success must not be presented as an unbounded proof.

## Review and limits

The separate `review` stage requires both simulation and formal records plus
`verification/REVIEW.md`. Do not create fake formal records for simulation-only
work. Every selected stage still requires independent review of its evidence.

The machine checker establishes record consistency, not oracle independence,
log authenticity, sufficient coverage or adequate formal assumptions. Review
the actual testbench, command execution and provenance as well as running the
checker. Do not mutate the operator's RTL to test an oracle without permission;
use a private copy if a mutation check is needed.
