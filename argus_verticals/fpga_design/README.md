# FPGA design

Independent domain `hardware / fpga_design`, with explicit knowledge dependencies
on both `digital_circuit` and `digital_circuit_verification`. Parent skills are
directly declared because Argus does not recursively seed grandparents.
`vertical.json` owns its store version and dependencies. Argus must expose
`VerticalPlugin.routing_path` before this provider can load.

This initial implementation supports **single-clock iCE40** projects using
Yosys, nextpnr-ice40 and IceStorm. Knowledge covers broader FPGA concerns, but
Vivado/Quartus, multiclock closure, DDR/PCIe hard IP and other device families do
not yet have accepted executable adapters. Do not disguise that boundary with
generic result JSON.

## Scopes

`requirements` freezes the target; `rtl` performs requirements, RTL and
verification; `verification` checks an existing target; `implementation` adds
actual synthesis/place-and-route/bitstream construction; `bringup` adds measured
board behavior; explicit `full` includes all six stages and delivery notes.
Custom goals add necessary verification/implementation companions. An RTL-only
scope requires no FPGA tools or connected board.

## Target and verification

`design/FPGA_TARGET.json` declares:

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

The example is a schema illustration, **not an approved board pinout**. Confirm
part/package, oscillator, pin connections, I/O-bank voltage and load before
programming. Supported part flags are `hx1k`, `hx8k`, `lp8k`, `up5k`.
`sources` are plain project-relative `.v`/`.sv` paths without whitespace.

Use the verification specialty's [evidence contract](../digital_circuit/verification/evidence-contract.md)
for `PLAN.json` / `RESULTS.json`. Its canonical text is included in every role's
verification-stage prompt, along with a read-only check of this FPGA provider.
The host's existing round-evidence hook runs the selected stage checker and
provides the result to the read/search-only Reviewer; no Reviewer shell or
board programming is required. This is evidence checking, not a new native
implementation or scientific execution. The result's input snapshots must
additionally include the target and every target
source. Changing a clock target or source invalidates that result. The included
FIFO regression demonstrates the RTL/verification path; adapt the top-level
ports and independently chosen cases for a board design.

Explicit `"cdc": true` in the verification plan additionally requires the
specialty's original-input-bound CDC/reset adapter study and a **passing**
structural/trace result; a negative diagnosis cannot qualify implementation.
Its native replay and snapshots are enforced by the same shared verification
checker. Use the independent specialty's `cdc` profile for a CDC-only task with
no board target. This does not extend the single-clock implementation backend,
prove complete CDC/RDC safety or authorize programming.

## Implementation

Write `constraints/board.pcf` with exactly one `set_io port pin` per top-level
port bit, matching the target. Do not use unconstrained-pin or timing-failure
waivers. With the tools installed and a successful verification record:

```bash
python -m argus_verticals.fpga_design.run_implementation /path/to/project
```

For a Store-only installation, prepend its resolved directory for this separate
Python process (Argus's in-process discovery does not change child-process paths):

```bash
STORE_ROOT="$(python -c 'from argus.verticals.store import store_root; print(store_root())')"
PYTHONPATH="$STORE_ROOT${PYTHONPATH:+:$PYTHONPATH}" python -m argus_verticals.fpga_design.run_implementation /path/to/project
```

The command refuses an existing `implementation/` directory: preserve the old
result before an intentional rerun. It never programs a board. It produces
`BUILD.json`, exact argv/exit codes/logs, input and output copies, Yosys `design.json`,
nextpnr `timing.json` and `design.asc`, then IceStorm `design.bin`.
The checker reads native [nextpnr report fields](https://github.com/YosysHQ/nextpnr/blob/main/common/kernel/report.cc),
checks all resources against capacity, checks the actual constraint against the
requested frequency, and rejects a missed frequency or zero/multiple reported
clocks. It also compares PCF pins with the target and synthesized top.
Changed or replaced implementation output no longer matches its retained copy
and must be rebuilt. These comparisons detect changed files, not fraudulent
records; independent review still checks tool and source provenance.

Fmax is not universal timing closure: this initial adapter does not certify I/O
delay budgets, CDC/RDC, hold timing, electrical limits, power, thermal behavior or
board functionality. Preserve these limits in `delivery/README.md`. A later
vendor/multiclock adapter must own its native timing and constraint checks.

## Board measurements

Programming requires explicit operator permission and correct electrical setup;
neither a successful build nor a JSON permission string authorizes programming.
The bundled command does not perform that operation.

`bringup/RESULTS.json` records `board`, physical `device_id`, `connection`, the
operator's `programming_permission`, current `inputs` for target/bitstream/build
record, and a `measurement` command/exit code/log. Real measurement output uses
`MEASURE <name> <number>`; each predeclared `bringup_checks` entry sets finite
inclusive `minimum` / `maximum` limits. Missing, duplicate, nonfinite or
out-of-range observations fail. Independent review checks device provenance,
permission and measurement setup; manually typed numbers cannot establish
physical execution. No connected board means no accepted bring-up claim.
