---
name: fpga_design
description: "FPGA board projects, resource inference, pin/clock constraints and bring-up; executable single-clock iCE40 implementation and hardware measurements, scoped RTL verification or full board delivery; not ASIC physical design or GPU kernels"
version: 0.2.0
---

# fpga_design

FPGA board projects, resource inference, pin/clock constraints and bring-up; executable single-clock iCE40 implementation and hardware measurements, scoped RTL verification or full board delivery; not ASIC physical design or GPU kernels.

## What counts as done

### requirements

- **requirements.target** — Board, part, clock, pins, electrical limits and acceptance conditions are explicit.
  Evidence hint: design/FPGA_TARGET.json

### rtl

- **rtl.sources** — All declared RTL sources implement the target interfaces.
  Evidence hint: RTL sources from design/FPGA_TARGET.json

### verification

- **verification.regression** — The target-bound parameter and scenario matrix passes independent comparisons.
  Evidence hint: verification/PLAN.json and verification/RESULTS.json

### implementation

- **implementation.native-results** — The constrained iCE40 implementation fits resources and reaches its specified clock frequency.
  Evidence hint: implementation/BUILD.json and native nextpnr timing.json

### bringup

- **bringup.measurements** — The authorized physical device produces the declared observations using the current bitstream.
  Evidence hint: bringup/RESULTS.json and measurement output

### delivery

- **delivery.reproduction** — The board result is reproducible and its timing, electrical and environmental limits are stated.
  Evidence hint: delivery/README.md

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' check --project-root . --stage verification
python3 '<this folder>/run_implementation.py' .
python3 '<this folder>/run_fifo_reference.py' <new directory>
```

Work only the smallest scope the task asks for and check its stages; omitted stages need no placeholder records: `requirements` (requirements), `rtl` (requirements, rtl, verification), `verification` (verification of existing RTL), `implementation` (verification, implementation; no board programming), `bringup` (verification, implementation, bringup) or `full` (all six). The record formats are in [records.md](records.md).

`evidence.py check --stage <stage>` is read-only and checks one stage cumulatively: `requirements` the target; `rtl` the target and its existing sources; `verification` the target, plan, input copies and every run's `CHECK`/`PASS regression` log; `implementation` adds BUILD.json, the exact Yosys/nextpnr/icepack commands, PCF pins against target and netlist, one timed clock reaching the target frequency and resources within capacity; `bringup` adds `MEASURE` lines within the declared limits for the current bitstream; `delivery` adds `delivery/README.md`. Exit 0 prints `fpga_design evidence valid for <stage>`; exit 1 prints `ERROR: <first issue>`; exit 2 is a usage error. Exit 0 means record consistency only, not that the work is right ([hardware-evidence-review.md](skills/reviewer/hardware-evidence-review.md)). Repair reported issues and rerun affected checks; explain what prevents completion, never weaken acceptance or forge records.

`run_implementation.py <project>` needs `yosys`, `nextpnr-ice40` and `icepack` on `PATH` and a passing verification check. It refuses an existing `implementation/` directory, runs synthesis, place-and-route and bitstream packing, retains logs and input/output copies in `implementation/BUILD.json`, then runs the implementation check. Exit 0 prints `PASS: ...`; exit 1 prints `FAIL: <reason>` (missing tool, failed check or tool, existing output). It never programs a board.

`run_fifo_reference.py <new directory>` needs Icarus Verilog (`iverilog`, `vvp`). It creates the reference FIFO regression (12 width/depth/seed configurations, 6 cases) in a new directory and checks its plan and results with the verification rules (it has no FPGA target). Exit 0 prints `PASS: ...`; exit 1 prints `FAIL: <reason>`. Use it as a worked example of independent scoreboard records.

## Needs

Python 3.10+; the bundled scripts use only the standard library. Verification needs a Verilog simulator (the reference regression uses Icarus Verilog `iverilog`/`vvp`). Implementation needs the open-source Yosys, nextpnr-ice40 and IceStorm `icepack` on `PATH` under exactly the names `yosys`, `nextpnr-ice40` and `icepack` (the check compares the recorded argv) and targets iCE40 hx1k/hx8k/lp8k/up5k only; no vendor license is used. Bring-up needs the physical board, a measurement setup and the operator's explicit permission to program it. The `requirements`, `rtl` and `verification` scopes need no FPGA tools or board. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [fpga-board-bringup.md](skills/engineer/fpga-board-bringup.md)

- engineer: [fpga-engineering-map.md](skills/engineer/fpga-engineering-map.md)

- engineer: [fpga-resources-timing.md](skills/engineer/fpga-resources-timing.md)

- engineer: [verification-matrix.md](skills/engineer/verification-matrix.md)

- manager: [fpga-scope.md](skills/manager/fpga-scope.md)

- reviewer: [fpga-acceptance.md](skills/reviewer/fpga-acceptance.md)

- reviewer: [hardware-evidence-review.md](skills/reviewer/hardware-evidence-review.md)

- reviewer: [verification-acceptance.md](skills/reviewer/verification-acceptance.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence.py](evidence.py)

- [fifo_reference/stream_fifo.sv](fifo_reference/stream_fifo.sv)

- [fifo_reference/stream_fifo_tb.sv](fifo_reference/stream_fifo_tb.sv)

- [records.md](records.md)

- [run_fifo_reference.py](run_fifo_reference.py)

- [run_implementation.py](run_implementation.py)
