# Independent digital verification

`digital_circuit_verification` is an independently selectable specialty under
`hardware / digital_circuit`. It reuses `digital_circuit` knowledge but never
inherits its RTL-creation or synthesis stages. Its code dependency is that parent
vertical; FPGA projects reuse this specialty's execution record checks.
Common file/copy/numeric checks live in `argus_verticals.hardware.shared` and
are bundled by its manifest. Existing imports from this specialty's `evidence`
module remain valid; shared code does not imply any workflow inheritance.
`vertical.json` declares its store version and dependency. It requires an Argus
build exposing `VerticalPlugin.routing_path`; older frameworks reject it with
an explicit upgrade message.

## Scope

| Profile | Stages | Result |
| --- | --- | --- |
| `plan` | plan | Requirement/case/configuration matrix for existing sources |
| `simulation` | simulation | Executed matrix with nonzero independent comparisons |
| `formal` | formal | Declared bounded/inductive checks plus reached cover traces |
| `cdc` | simulation | Native declared single-bit level/reset structures and finite clock/phase traces |
| `full` | plan, simulation, formal, review | Both methods and a review of their limits |

Custom combinations use the existing Argus scope mechanism. Simulation and
formal goals require a valid plan manifest. Reuse an applicable existing plan;
when absent, prepare the manifest from the supplied requirements within the
selected execution stage, without adding a standalone plan stage. Review requires
both methods; choose a narrower scope rather than inventing N/A formal results.
The optional `cdc` profile instead uses `verification/CDC_PLAN.json` and a
separate original specification; it does not require general matrix/formal
records. It checks a bounded, completely declared synchronizer adapter, not all
crossings in an arbitrary design. The legacy `full` profile stays unchanged.
No profile establishes complete CDC/RDC sign-off, STA closure, DFT coverage,
analog behavior, metastability/MTBF qualification or certification.

With native Yosys and Icarus Verilog installed, the separate CDC/reset reference
is runnable in a new directory:

```bash
python -m argus_verticals.digital_circuit.verification.run_cdc_reference /tmp/new-cdc-study
```

It checks source-faster, destination-faster and coincident-edge schedules, native
stage counts and fanout, asynchronous reset assertion and domain-local release.
The canonical contract below defines the two/three-stage adapter boundary,
diagnosis versus design goals, independent raw traces and native replay. Use
`"cdc": true` in an existing general/FPGA verification plan only when explicitly
composing this additional work; composition requires a passing CDC result.

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
