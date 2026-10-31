# FPGA records

These are the files `evidence.py` reads. All paths are relative to the project,
stay inside it and name nonempty files; do not use absolute paths or `..`.
The examples are schema illustrations, not completed results: substitute the
actual target, sources, requirements, cases and complete configuration matrix.

This flow supports **single-clock iCE40** projects with Yosys, nextpnr-ice40 and
IceStorm. Vivado/Quartus, multiclock closure, DDR/PCIe hard IP and other device
families have no accepted executable check here. Do not disguise that boundary
with generic result JSON. An RTL-only scope needs no FPGA tools or board.

## Target: `design/FPGA_TARGET.json`

```json
{
  "top": "blink",
  "board": "operator-supplied board identifier",
  "part": "up5k",
  "package": "sg48",
  "clock": {"port": "clk", "frequency_mhz": 12},
  "sources": ["rtl/blink.sv"],
  "pins": {"clk": "35", "led": "11"},
  "io_voltage_v": 3.3,
  "limitations": ["Example pin values must be checked against the actual board schematic"],
  "bringup_checks": {"led_frequency_hz": {"minimum": 0.9, "maximum": 1.1}}
}
```

The example is **not an approved board pinout**. Confirm part/package,
oscillator, pin connections, I/O-bank voltage and load before programming.
Supported part flags are `hx1k`, `hx8k`, `lp8k`, `up5k`. `top` is a Verilog
module identifier. `sources` are distinct plain project-relative `.v`/`.sv`
paths without whitespace. `pins` maps every top-level port bit (`data[3]` for
a bus bit), including the clock port, to a distinct package pin. `limitations`
is a nonempty list. `bringup_checks` is needed only for bring-up.

## Verification: `verification/PLAN.json` and `verification/RESULTS.json`

The plan records the inputs and acceptance matrix:

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

If the check consumes an external numerical contract, an oracle/helper module
or retained input fixtures, declare those additional project files explicitly:

```json
{"supporting_files": ["design/numerical-contract.json", "reference/oracle.py", "verification/fixtures/input.hex"]}
```

This optional field is a distinct, nonempty list of existing project-relative
files. Every listed file must have an independent current byte copy in the
results, just like sources and testbenches. Declaration does not discover the
evaluator's transitive dependencies or prove its independence; review the
actual consumed inputs. Do not change original tolerances or precision rules
while making the plan. The plan's optional `cdc` key must be a boolean, and
`"cdc": true` fails: this pack has no CDC/reset adapter checker.

Reuse an applicable existing plan. If absent, write it from the provided
requirements while preparing the requested tests; ask about genuinely
unresolved requirements rather than inventing them. Merely naming a
nonexistent testbench is not a valid plan.

The results have this structure:

```json
{
  "inputs": {
    "verification/PLAN.json": "verification/inputs/PLAN.json",
    "design/FPGA_TARGET.json": "verification/inputs/FPGA_TARGET.json",
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

`inputs` maps the plan, every source, testbench and supporting file, **plus
`design/FPGA_TARGET.json` and every target source**, to an independent,
byte-identical copy. Self-copies, hardlinks and paths escaping the project are
invalid. Copy the inputs used for the run; a change to any of them (including
the clock target) invalidates the result and requires rerunning affected checks,
not merely copying changed files over old snapshots.

`runs` contains exactly one record per planned configuration, with no
omissions, duplicates or extras. `command` is the actual argv list, not a shell
command string. `exit_code` is the actual integer zero, not a boolean. Preserve
compilation commands/output too, for example as extra run fields or build logs.

Instrument the independent scoreboard to emit, in each configuration's raw log:

```text
CHECK reset 3
CHECK transfer 200
CHECK stall 50
PASS regression
```

The numbers illustrate the format only. Emit exactly one
`CHECK <case> <positive-count>` for **every** planned case and no other case IDs.
Counters must count actual successful comparisons, not elapsed cycles or
unconditional increments. Emit exactly the line `PASS regression` only after
the checks finish successfully. Preserve raw tool output; any `FATAL`, `ERROR`
or `FAIL` marker rejects the result. A normal exit, an aggregate PASS line or a
Markdown report is insufficient. Counts are not coverage closure.
`run_fifo_reference.py` produces a complete worked example of these two files
(without an FPGA target).

## Implementation: `constraints/board.pcf` and `implementation/`

Write `constraints/board.pcf` with exactly one `set_io <port> <pin>` per
top-level port bit, matching the target's `pins`. Do not use unconstrained-pin
or timing-failure waivers. With the tools installed and a passing verification
check, run `run_implementation.py` once. It refuses an existing
`implementation/` directory: preserve the old result before an intentional
rerun. It never programs a board. It writes `implementation/BUILD.json` with
`inputs` (copies of target, PCF, sources, plan, results and run logs),
`commands` (`synthesis`, `place_route`, `bitstream`: exact argv, exit code, log)
and `outputs` (copies of `design.json`, `timing.json`, `design.asc`,
`design.bin`). The flow commands are fixed:

```text
yosys -p "read_verilog -sv <sources>; synth_ice40 -top <top> -json implementation/design.json"
nextpnr-ice40 --<part> --package <package> --json implementation/design.json --pcf constraints/board.pcf --freq <frequency_mhz> --seed 1 --asc implementation/design.asc --report implementation/timing.json
icepack implementation/design.asc implementation/design.bin
```

The check reads native [nextpnr report fields](https://github.com/YosysHQ/nextpnr/blob/main/common/kernel/report.cc):
exactly one timed clock whose constraint equals the requested frequency and
whose achieved Fmax reaches it, and every resource within capacity with
nonzero total use. It also compares PCF pins with the target and the
synthesized top's ports, and requires the clock to be a scalar input. Changed
or replaced implementation output no longer matches its retained copy and must
be rebuilt. These comparisons detect changed files, not fraudulent records;
independent review still checks tool and source provenance.

Fmax is not universal timing closure: this flow does not certify I/O delay
budgets, CDC/RDC, hold timing, electrical limits, power, thermal behavior or
board functionality. Preserve these limits in `delivery/README.md`.

## Bring-up: `bringup/RESULTS.json`

Programming requires explicit operator permission and correct electrical setup;
neither a successful build nor a JSON permission string authorizes programming.
No bundled script programs a device.

`bringup/RESULTS.json` records `board` (equal to the target's), physical
`device_id`, `connection`, the operator's `programming_permission`, `inputs`
with current copies of `design/FPGA_TARGET.json`, `implementation/design.bin`
and `implementation/BUILD.json`, and a `measurement` object with argv
`command`, integer `exit_code` and `log`. Real measurement output uses lines
`MEASURE <name> <number>`; each name declared in the target's `bringup_checks`
appears exactly once, within its finite inclusive `minimum` / `maximum`.
Missing, duplicate, unplanned, nonfinite or out-of-range observations fail.
Manually typed numbers cannot establish physical execution. No connected board
means no accepted bring-up claim.

## Delivery: `delivery/README.md`

Delivery passes the bring-up check plus a nonempty `delivery/README.md` stating
how to reproduce the board result and its timing, electrical and environmental
limits.
