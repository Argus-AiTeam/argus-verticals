# Independent digital verification

`digital_circuit_verification` is an independently selectable specialty under
`hardware / digital_circuit`. It reuses `digital_circuit` knowledge but never
inherits its RTL-creation or synthesis stages. Its code dependency is that parent
vertical; FPGA projects reuse this specialty's execution record checks.
`vertical.json` declares its store version and dependency. It requires an Argus
build exposing `VerticalPlugin.routing_path`; older frameworks reject it with
an explicit upgrade message.

## Scope

| Profile | Stages | Result |
| --- | --- | --- |
| `plan` | plan | Requirement/case/configuration matrix for existing sources |
| `simulation` | simulation | Executed matrix with nonzero independent comparisons |
| `formal` | formal | Declared bounded/inductive checks plus reached cover traces |
| `full` | plan, simulation, formal, review | Both methods and a review of their limits |

Custom combinations use the existing Argus scope mechanism. Simulation and
formal goals require a valid existing plan, not its recreation. Review requires
both methods; choose a narrower scope rather than inventing N/A formal results.
This specialty does not establish CDC structural safety, STA closure, DFT
coverage, analog behavior, or certification.

## Runnable reference

With Icarus Verilog installed:

```bash
python -m argus_verticals.digital_circuit.verification.run_reference /tmp/new-fifo-regression
```

When installed only through the Vertical Store (not pip), expose that resolved
store directory to the separate Python process:

```bash
STORE_ROOT="$(python -c 'from argus.verticals.store import store_root; print(store_root())')"
PYTHONPATH="$STORE_ROOT${PYTHONPATH:+:$PYTHONPATH}" python -m argus_verticals.digital_circuit.verification.run_reference /tmp/new-fifo-regression
```

The destination must not exist. The command copies the reference sources,
compiles and runs **12** explicit configurations: widths 1/8, depths 1/3/8,
seeds 1/7. It checks reset, ordered transfers, output stalls, full/empty state,
and simultaneous enqueue/dequeue. It preserves failed command output and exits
nonzero on failure. It is a single-clock teaching FIFO, not an asynchronous FIFO
or production-qualified memory primitive. See the independent scoreboard and
implementation in `skills/engineer_scripts/`.

## Execution record

`verification/PLAN.json` names nonempty `sources`, `testbenches`,
`configurations`, `cases`, and `requirements` mapping requirements to cases.
Cases use lowercase underscore identifiers. Configuration names must explicitly
identify the parameters and seed; the reviewer checks the corresponding compile
and simulation arguments rather than trusting a label.

`verification/RESULTS.json` contains `inputs` (project-relative source-to-snapshot
file mapping) and `runs`. Each run has the exact `configuration`, argument-vector
`command`, integer zero `exit_code`, and `log`. An instrumented independent
scoreboard emits one `CHECK <case> <positive-comparison-count>` for each planned
case and `PASS regression` only after comparisons finish. Repeated/missing
configurations, zero checks, contradictory failure output and changed inputs
prevent completion. Testbench and plan changes invalidate prior results too.
Counters measure executed comparisons, not code coverage or proof completeness.

Formal plans additionally declare `formal.mode` (`bmc` or `prove`), positive
`depth`, `assertions`, `covers`, and an `assumptions` list with `expression` and
`reason` (explicit `[]` is allowed). `verification/FORMAL.json` records `inputs`
and exact assertion/cover maps. Each entry includes `mode`, `depth`, `command`,
`exit_code`, and a successful native SymbiYosys `log`; every cover also names a
nonempty `witness`. Preserve the property harness and SBY configuration in the
plan's inputs. A bounded success is never presented as an unbounded proof.

These checks establish consistency and reject incomplete execution records;
they cannot establish that an arbitrary testbench is independent, that manually
supplied logs are authentic, or that assumptions describe the intended system.
Argus's independent review remains required. The bundled runnable example is
simulation-based; it is not evidence that a formal toolchain was installed.
