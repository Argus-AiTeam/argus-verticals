# Required verification records

All file paths below are relative to the execution project, remain inside it,
and identify nonempty files. Do not use absolute paths or `..` in record paths.
These are schema examples, not completed results. Substitute the operator's
actual sources, requirements, cases and complete configuration matrix.

## Plan manifest: required for the general simulation scope

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

## Optional declared CDC/reset adapter study

The `cdc` workflow profile uses the existing `simulation` stage with a different,
explicit input contract. It requires **only** `verification/CDC_PLAN.json` and
its original specification/RTL, not the general `PLAN.json`, FIFO regression or
formal records above. The legacy `full` profile is unchanged; it does not silently
add CDC work. Use the profile-specific read-only command supplied in the stage
prompt, rather than the general matrix checker.

`verification/CDC_PLAN.json` contains exactly:

```json
{"specification": "design/cdc-study.json"}
```

The external original specification owns the goal, top, source list, complete
scalar port/domain inventory, clock configurations and requirements. Do not
rewrite it or the operator's RTL to make checks pass. This bounded adapter
supports two to four independent positive-edge clocks, one to four single-bit
level crossings, and one active-low asynchronous-assert/synchronous-release reset
chain per clock. Each data path has **one source-domain launch register followed
by exactly two or three destination-domain registers**. Each uses the local
synchronized reset for its domain. Each reset chain has two or three stages,
asynchronous zero reset, and a constant-one release input.

There are no other top-level ports, data logic, state, waivers or black boxes in
the accepted adapter model. It is suitable for a separately declared adapter
top, not for claiming an arbitrary SoC has no undiscovered crossings. Rejected
structures mean the original adapter requirements were not met; they do not
prove every alternative CDC architecture unsafe.

Example original specification (the RTL must implement these actual ports):

```json
{
  "goal": "design",
  "top": "cdc_reference",
  "sources": ["rtl/cdc_reference.sv"],
  "clocks": ["clk_src", "clk_dst"],
  "resets": {
    "clk_src": {"input": "arst_n", "output": "reset_src_n", "stages": 2},
    "clk_dst": {"input": "arst_n", "output": "reset_dst_n", "stages": 2}
  },
  "crossings": {
    "status_level": {
      "input": "level_in", "output": "level_out",
      "source_clock": "clk_src", "destination_clock": "clk_dst", "stages": 2
    }
  },
  "configurations": {
    "source_fast": {
      "clk_src": {"period_ticks": 10, "phase_ticks": 0},
      "clk_dst": {"period_ticks": 14, "phase_ticks": 3}
    },
    "destination_fast": {
      "clk_src": {"period_ticks": 18, "phase_ticks": 4},
      "clk_dst": {"period_ticks": 8, "phase_ticks": 1}
    }
  },
  "requirements": {
    "level_latency": "Source launch then exactly two destination edges; no early-stage use.",
    "reset_assert": "Local resets assert asynchronously, including between clock edges.",
    "reset_release": "Each reset releases after exactly two edges of its own clock."
  },
  "limitations": ["Ideal digital level transport; no physical CDC or metastability claim."]
}
```

All listed fields are required; unknown fields are rejected rather than treated
as waivers. Plain project-relative `.v`/`.sv` inputs are limited to 16 files and
256 KiB total. Includes, macros, external data files and simulation system tasks
are not supported; `timescale`, `default_nettype`, `$clog2` and `$bits` are allowed.
The specification is at most 64 KiB. Port/module/configuration identifiers are
plain RTL identifiers. Ports are distinct, except a reset input may be shared
by several domains; separate reset inputs are also supported.
There must be two to eight distinct complete clock configurations, each with
even integer periods from 8 to 64 ticks and integer phases from zero through
period minus one. Clocks are initially low and first rise at phase plus one;
one tick is one simulated nanosecond, not a qualified operating frequency.

Execute with native Yosys and Icarus Verilog installed:

```bash
python -m argus_verticals.digital_circuit.verification.cdc /path/to/project
```

For Store-only child processes expose the resolved Store directory through
`PYTHONPATH`, or use the loader-based execution command in the role prompt.
The runner refuses an existing `verification/cdc/` directory. Preserve old
results before a deliberate rerun; never overwrite snapshots to conceal changed
inputs. Native tool failure, missing ports that prevent elaboration, missing
traces or invalid declarations are incomplete work, not accepted diagnoses.

The runner extracts a flattened native Yosys netlist without register merging,
checks clock/reset polarity, chain length, complete sequential-state inventory,
direct data connections and intermediate-stage fanout. Digital traces alone
cannot substitute for these structural checks: raw-reset usage can look correct
in simulation while still failing the declared synchronization structure.
Each structural `finding` identifies the path, failure kind and, when available,
native cell, bit and RTL source position. Clock/reset connection findings also
give the expected signal and observed native net aliases. A failed clock or
reset check does not stop traversal of the remaining directly connected stages.
`traces` includes inspected paths even when they fail; only fully accepted paths
appear in `chains`. Unreachable state is reported separately, not automatically
counted as another defect merely because a traced chain failed.
It then compiles/runs an independently generated Icarus stimulus for **every**
original configuration. Stable low/high transitions, staggered initial reset
release and an individual mid-traffic pulse on every reset input are exercised.
Later reset assertions/releases occur between every domain's active edges.
With multiple data inputs, the stimulus additionally holds each input high on
its own and low on its own long enough for the declared chains to settle.
This makes input swaps observable even when identical simultaneous transitions
would conceal them. `data_patterns` records the input order and exercised value
patterns; it is not a claim of complete input-combination coverage.
The host compares every output at every tick against a separate synchronous
state/history calculation, including coincident-clock old-value semantics and
unknown outputs. Counts are actual comparisons, not elapsed cycles.

`verification/cdc/RESULTS.json` records exact native argv, integer exits, raw
logs, independent original input copies, and retained generated netlist,
testbenches, executables, traces and `ASSESSMENT.json`. The assessment contains
structural findings, per-configuration comparison/mismatch counts and first
counterexample ticks. Execution is bounded to 180 seconds per study, 30 seconds
per command and 128 MiB generated files before retained copies.
Time and generated-output limits are checked while the native command is still
running, with 50 ms sampling, and again after it exits. A process may produce
additional bytes between samples; 128 MiB is a stop threshold, not a filesystem
quota. On POSIX the runner terminates only that command's own process group;
it records the actual exit code and `stop_reason` before reporting failure.
Timeouts and output overruns cannot become valid negative engineering diagnoses.
The read-only checker recomputes the assessment, executes a fresh native replay
in a temporary directory, and compares the native netlist, generated stimuli
and raw traces without changing the project. Compiled Icarus files contain
process-specific addresses; retaining them is not a bit-identical rebuild claim.
Version 0.2.1 adds independent multi-input stimuli and detailed structural
findings. Preserve previously accepted 0.2.0 results with their generating
provider; create fresh results for the new checker rather than rewriting old
snapshots or claiming that the old experiment exercised the new patterns.

`goal: "diagnose"` may finish with `status: "failed"` and
`task_accepted: true` after complete, valid execution: report the negative
engineering conclusion and witnesses. `goal: "design"` requires all declared
structures and all trace comparisons to pass. There is no acceptance waiver.
Independent Reviewer inspection of the source, original inventory, model limits
and real tool execution remains necessary even after the machine check passes.

For explicitly **composed** general or FPGA verification, set `"cdc": true` in
the general `verification/PLAN.json`. Its source list must include all CDC
sources. Simulation/formal input snapshots must additionally include the
`CDC_PLAN.json`, external specification, CDC sources, and CDC `RESULTS.json` and
`ASSESSMENT.json`. The composed check requires CDC engineering status **passed**;
an accepted negative diagnosis cannot establish design/implementation success.
The standalone `cdc` profile does not require a board target or physical tools.
FPGA implementation remains single-clock iCE40; this feature adds neither
multiclock place-and-route nor board programming.

Limits: no metastability waveform model or injection claim, MTBF estimate,
placement/attributes sign-off, STA/skew constraint validation, pulses, coherent
buses, asynchronous FIFO verification, analog behavior, or complete CDC/RDC
closure. Finite phase samples and logical reset behavior are not physical safety
certification. Preserve these limits in the report.
