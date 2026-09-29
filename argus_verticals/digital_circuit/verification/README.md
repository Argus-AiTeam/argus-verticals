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
formal goals require a valid plan manifest. Reuse an applicable existing plan;
when absent, prepare the manifest from the supplied requirements within the
selected execution stage, without adding a standalone plan stage. Review requires
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

The canonical [evidence contract](evidence-contract.md) defines the exact plan,
simulation and formal record shapes with examples. The provider injects this
same document into the Manager, Planner, Engineer and Reviewer stage prompts;
acceptance requirements do not depend on optional skill retrieval. It also
supplies a read-only check using Argus's own Python and vertical loader, which
works with Store-only installations without manual namespace setup. Engineer
and Reviewer must run it from the execution project before approval. A
Reviewer `done` or passing simulation alone cannot replace provider acceptance.

These checks establish consistency and reject incomplete execution records;
they cannot establish that an arbitrary testbench is independent, that manually
supplied logs are authentic, or that assumptions describe the intended system.
Argus's independent review remains required. The bundled runnable example is
simulation-based; it is not evidence that a formal toolchain was installed.
