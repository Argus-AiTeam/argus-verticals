---
name: digital_circuit
description: "digital logic and cycle-accurate Verilog/SystemVerilog RTL: combinational/sequential circuits, arithmetic, FSMs, FIFOs, interfaces, CDC, verification and synthesis; not CUDA/Triton kernels or whole-chip architecture"
version: 1.2.0
---

# digital_circuit

digital logic and cycle-accurate Verilog/SystemVerilog RTL: combinational/sequential circuits, arithmetic, FSMs, FIFOs, interfaces, CDC, verification and synthesis; not CUDA/Triton kernels or whole-chip architecture.

## What counts as done

A task has to meet only the stages its request covers: RTL work also needs specification and verification, synthesis needs verification, and delivery needs every earlier stage. The [knowledge map](skills/engineer/digital-knowledge-map.md) lists the usual scopes.

### specification

- **spec.behavior-interface** — The cycle-level functional behavior and complete module interface are explicit, including port direction, width, signedness, parameters, and legal value ranges. A public benchmark interface is preserved exactly unless the prompt explicitly requests its repair; every unresolved ambiguity is recorded.
  Evidence hint: design/SPEC.md with behavior tables and a port/parameter table

- **spec.clock-reset-protocol** — Clock domains, reset polarity and sync/async behavior, reset values, handshake timing, backpressure, latency, and throughput expectations are explicit.
  Evidence hint: timing diagrams or cycle tables plus reset and protocol rules

- **spec.acceptance-matrix** — Normal, boundary, illegal, reset, stall, and recovery scenarios are mapped to observable expected results before implementation begins.
  Evidence hint: a scenario-to-expected-result verification matrix

- **spec.benchmark-interface-closure** — For an external RTL benchmark, exact output path, top module, ports, parameters, reset/clock semantics, control interpretation, and cycle latency are frozen before generation; otherwise the record explicitly states that no external benchmark contract applies.
  Evidence hint: design/BENCHMARK_INTERFACE.json derived only from public prompt/context and output schema, or an explicit non-benchmark statement

### rtl

- **rtl.spec-traceability** — Every state element, datapath operation, and interface response traces to the frozen specification; benchmark output filenames and module/port/parameter identifiers exactly match the interface manifest, and implementation does not silently redefine behavior.
  Evidence hint: RTL review notes mapping modules and state transitions to spec clauses

- **rtl.synthesizable-discipline** — Synthesizable RTL uses complete combinational assignments and disciplined sequential logic, with no unintended latches, multiple drivers, unsafe CDC, or simulation-only constructs in the design path.
  Evidence hint: lint output and reviewer inspection of rtl/**/*.sv or src/**/*.v

- **rtl.width-reset-parameters** — Width extension/truncation, signed arithmetic, reset state, counter overflow, array bounds, and parameter edge cases are intentional and verified.
  Evidence hint: lint findings plus targeted elaboration or compile configurations

### verification

- **verify.independent-oracle** — The testbench or formal model checks behavior against an independent oracle, assertion set, or reference model rather than reproducing the RTL algorithm.
  Evidence hint: self-checking scoreboard/reference model or named formal properties

- **verify.reset-boundary-random** — Verification covers reset entry/exit, boundaries, protocol stalls, illegal inputs where defined, exact width/signing, combinational versus prior-state sequential semantics, reset polarity/synchronicity, latency, initialization uncertainty, and randomized, exhaustive, or metamorphic cases appropriate to the public design.
  Evidence hint: verification plan and fresh run log with scenario counts/seeds

- **verify.no-xz-and-properties** — Assertions detect X/Z leakage, protocol violations, overflow/underflow hazards, and safety/liveness properties relevant to the module.
  Evidence hint: SVA/assertion sources and simulator or formal-engine results

- **verify.reproducible-pass** — A clean, documented command reproduces compile/elaboration and all claimed PASS results; failures retain actionable logs or waveforms.
  Evidence hint: verification/RESULTS.md plus raw logs and the exact command

### synthesis

- **synth.target-constraints** — The synthesis target, tool/version, clock definitions, I/O delays, generated clocks, and other timing constraints are explicit and appropriate.
  Evidence hint: synthesis script/constraints and synthesis/REPORT.md

- **synth.structural-sanity** — Reports show no unexplained latches, combinational loops, undriven nets, multiple drivers, unresolved black boxes, or critical warnings.
  Evidence hint: lint/synthesis warning summary with every waiver justified

- **synth.timing-area** — Timing and area/resource claims cite fresh reports, including worst slack, clock target, utilization/cell area, and the tested parameter configuration.
  Evidence hint: timing and utilization/area report excerpts with source paths

### delivery

- **delivery.clean-reproduction** — A clean checkout can run the documented lint, simulation/formal, and synthesis commands without relying on private caches or undeclared files.
  Evidence hint: Makefile/justfile/scripts plus a clean reproduction log

- **delivery.traceable-results** — RESULTS.md or DELIVERY.md traces every correctness, coverage, timing, and area claim to raw tool output and names all unsupported or unverified behavior.
  Evidence hint: delivery summary with links to verification and synthesis outputs

- **delivery.source-artifact-boundary** — Source RTL, testbench/formal sources, constraints, generated netlists, waveforms, and reports are clearly separated so stale generated output cannot masquerade as source.
  Evidence hint: a manifest of the delivered files and repository status

- **delivery.benchmark-integrity** — When an external benchmark is claimed, task selection and scorer provenance are frozen, the delivered patch is non-empty, first-attempt evidence is immutable, repairs append separate records, and golden outputs or hidden harness sources were not exposed; otherwise delivery explicitly records that no external benchmark claim is being made. Every pre-existing public file referenced by the prompt was present before generation; missing context blocked the run rather than being reconstructed from evaluator feedback.
  Evidence hint: selection.json/controller.json plus append-only results.jsonl and per-attempt raw score directories, or an explicit non-benchmark statement in DELIVERY.md

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' specification --project-root .
python3 '<this folder>/evidence.py' rtl --project-root .
python3 '<this folder>/evidence.py' verification --project-root .
python3 '<this folder>/evidence.py' synthesis --project-root .
python3 '<this folder>/evidence.py' delivery --project-root .
python3 '<this folder>/evidence.py' benchmark-interface --project-root .
python3 '<this folder>/evidence.py' preflight --project-root .
```

Run the checks of the stages the task covers. Every file must be non-empty and inside the project; the delivery entry point only has to exist:

- `specification`: `design/SPEC.md`, `SPEC.md` or `docs/SPEC.md`.
- `rtl`: a `.v` or `.sv` file under `rtl/` or `src/`.
- `verification`: a `.v`, `.sv`, `.py` or `.sby` source under `tb/`, `testbench/`, `verification/`, `formal/` or `reference/`, plus, under `reports/` or `verification/`, a `.json` whose `status` is `pass`, `passed`, `proved`, `unsat` or `success` with no failure field, failing status or nonzero return code anywhere in it, or a `.log` with a line starting `PASS` (or `PASSED`, `PROVED`, `UNSAT`, `SUCCESS`, `status: pass`) and no fail/error/fatal word anywhere besides counts such as `0 errors` or `no failures`.
- `synthesis`: `synthesis/REPORT.md`, or a `*synth*.log`, `*timing*.rpt` or `*utilization*.rpt` (any letter case) under `reports/` or `synthesis/`. `synthesis/NOT_APPLICABLE.md` does not pass it: only in a `full` delivery may that note, giving the reason synthesis was not run, take the place of this check; a task that asks for synthesis needs a real report.
- `delivery`: `RESULTS.md` or `DELIVERY.md`, and a reproduction entry point `Makefile`, `justfile`, `run.sh`, `scripts/run.sh` or `scripts/verify.sh`.
- `benchmark-interface`: `design/BENCHMARK_INTERFACE.json` with `"status": "ready"`, top module(s), output path(s), non-empty ports and `schema_version` 1 or 2; version 2 also needs each port's name, direction, width and boolean `signed`, an `ambiguities` list, and `interface_change.requested` (with `public_request` when true). The schema is in [first-pass contract closure](skills/engineer/digital-circuit-first-pass-contract-closure.md).
- `preflight`: `evidence/preflight.json` with `"status": "pass"`, top module(s), RTL/artifact files and output paths that exist, and `compile_results` whose every `returncode` is 0. The schema is in [benchmark execution](skills/engineer/digital-circuit-benchmark-execution.md).

Exit 0 prints `OK: validated <file>`; exit 1 prints `FAIL: <reason>` on stderr. A pass shows the files are present and consistent, not that the RTL is correct, the oracle independent or the reported numbers real; check those against the items above in the sources and raw tool output.

## Needs

Python 3.10+; evidence.py uses only the standard library and needs no GPU. Simulation needs an HDL simulator (for example Icarus Verilog or Verilator, optionally cocotb), formal proof an engine such as SymbiYosys, and synthesis/timing a synthesis tool (for example Yosys or a vendor FPGA/ASIC flow) with its target device or cell library and any licenses; a fixed external benchmark needs its frozen evaluator and its simulator image (for example a local Docker image). Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [digital-arbitration.md](skills/engineer/digital-arbitration.md)

- engineer: [digital-arithmetic.md](skills/engineer/digital-arithmetic.md)

- engineer: [digital-cdc-rdc.md](skills/engineer/digital-cdc-rdc.md)

- engineer: [digital-circuit-benchmark-execution.md](skills/engineer/digital-circuit-benchmark-execution.md)

- engineer: [digital-circuit-error-guided-repair.md](skills/engineer/digital-circuit-error-guided-repair.md)

- engineer: [digital-circuit-first-pass-contract-closure.md](skills/engineer/digital-circuit-first-pass-contract-closure.md)

- engineer: [digital-circuit-rtl-verification.md](skills/engineer/digital-circuit-rtl-verification.md)

- engineer: [digital-circuit-spec-guidance-registry.md](skills/engineer/digital-circuit-spec-guidance-registry.md)

- engineer: [digital-fsm.md](skills/engineer/digital-fsm.md)

- engineer: [digital-handshake-pipelines.md](skills/engineer/digital-handshake-pipelines.md)

- engineer: [digital-knowledge-map.md](skills/engineer/digital-knowledge-map.md)

- engineer: [digital-logic-encoding.md](skills/engineer/digital-logic-encoding.md)

- engineer: [digital-low-power.md](skills/engineer/digital-low-power.md)

- engineer: [digital-memory-fifo.md](skills/engineer/digital-memory-fifo.md)

- engineer: [digital-parameters.md](skills/engineer/digital-parameters.md)

- engineer: [digital-sequential-reset.md](skills/engineer/digital-sequential-reset.md)

- engineer: [digital-synthesis-timing.md](skills/engineer/digital-synthesis-timing.md)

- engineer: [digital-verification-formal.md](skills/engineer/digital-verification-formal.md)

- reviewer: [digital-circuit-benchmark-review.md](skills/reviewer/digital-circuit-benchmark-review.md)

- reviewer: [digital-circuit-guidance-promotion-review.md](skills/reviewer/digital-circuit-guidance-promotion-review.md)

- reviewer: [digital-circuit-signoff-review.md](skills/reviewer/digital-circuit-signoff-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence.py](evidence.py)
