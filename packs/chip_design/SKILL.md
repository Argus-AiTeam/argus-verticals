---
name: chip_design
description: "digital ASIC/hardware accelerator subsystems: workload, microarchitecture, compute, memory/DMA, interconnect and host integration; bounded APB4 register/timer/interrupt control design, repair and diagnosis. For the fixed apb4-timer-v1 contract, the control profile already includes authorized RTL repair, native synthesis, both RTL/synthesized simulations and generic-cell limits within verification; these generic counts are not PPA and do not require custom rtl+ppa stages. Other requests use scoped architecture/RTL/PPA tasks or explicit full implementation and sign-off, not GPU software kernels"
version: 1.4.0
---

# chip_design

Digital ASIC and hardware-accelerator subsystem design (workload, microarchitecture, compute, memory/DMA, interconnect, host integration, PPA), plus bounded APB4 register/timer/interrupt control design, repair and diagnosis.

Every claim needs checkable evidence. This is not ordinary software work or GPU kernel programming. Delivery level describes the target; only completed, reviewed stages may be claimed as delivered: synthesizable IP, FPGA, open-PDK GDS, computer-verified pre-tapeout readiness, actual tapeout readiness and fabricated silicon are different claims. Freeze interfaces, numerical behavior, target technology, resource/power budgets, baselines and the metrics the finished design must meet before implementation. Numeric area, frequency, power, memory and quality targets belong to the operator: a plan, ledger or review may recommend a change but cannot authorize one, and relaxing a target needs the operator's explicit approval, recorded as such. Use maintained EDA flows and IP before authoring replacements. Never invent tool runs, coverage, PPA, power, DRC/LVS/STA, FPGA, silicon or market-comparison results.

Each piece of work runs under one workflow profile, which selects the stages below that apply: `architecture` (definition, architecture), `rtl` (definition, architecture, environment, rtl, verification), `verification`, `control` (the fixed `apb4-timer-v1` peripheral, inside verification), `ppa` (verification, ppa), `prototype` (verification, ppa, prototype), `benchmark` (verification, ppa, benchmark), `full` (all nine), or `custom` (requested stages plus their required companions). The Manager names the profile in its letter to the team; with none named it is `full`. Stages outside the profile are out of scope, not skipped or passed. See [workflow](references/workflow.md) and [scope selection](skills/manager/chip-scope-selection.md).

## What counts as done

### definition

- **definition.delivery-scope** — The delivery level, target workload, supported/non-supported operations, numerical formats, interfaces, target platform/technology, and non-goals are frozen.
  Evidence hint: design/CHIP_SCOPE.json and design/WORKLOAD.md

- **definition.acceptance-metrics** — The correctness, performance, power, area/resource, quality, and provenance standards the result must meet are measurable and distinguish IP, FPGA, GDS, tapeout, and market claims.
  Evidence hint: design/CHIP_SCOPE.json acceptance_metrics and design/SPEC.md

- **definition.baseline-fairness** — Open-hardware, software/system, and market-reference baselines are named with an explicit apples-to-apples comparison policy.
  Evidence hint: design/BASELINE_PLAN.md or a definition-stage baseline section

### architecture

- **architecture.compute-memory-model** — Compute, dataflow, memory hierarchy, DMA/NoC, external bandwidth, arithmetic intensity, and expected utilization are quantified for representative workload shapes.
  Evidence hint: design/ARCHITECTURE.md and design/MEMORY_MODEL.json

- **architecture.interface-control** — Host commands, register map, address/stride rules, interrupts, errors, reset/clock/CDC, backpressure, latency, and completion semantics are explicit.
  Evidence hint: design/SPEC.md interface and cycle tables

- **architecture.leverage-risk** — Amdahl/roofline leverage, implementation risks, IP reuse, verification strategy, and fallback or de-scoping decisions are recorded before RTL.
  Evidence hint: design/ARCHITECTURE.md design-tradeoff table

- **architecture.area-reuse-plan** — Area reuse is planned explicitly: mutually exclusive operators share or fold MACs, accumulators, requantization, vector/SFU, divide/round/saturate, DMA, buffers, and control where measured mux/control overhead preserves the PPA goal.
  Evidence hint: design/ARCHITECTURE.md lifetime/resource-sharing table with dedicated-versus-shared alternatives and expected cycle/area costs

### environment

- **environment.eda-capabilities** — A machine-readable record proves that the simulator, formal, synthesis, FPGA, physical-design, PDK, and compiler/runtime capabilities and the sign-off checks the active workflow profile and delivery level require are all ready. The rtl profile requires simulation and lint, not omitted implementation tools.
  Evidence hint: research/ENVIRONMENT_AUDIT.json

- **environment.tool-ip-selection** — Maintained tools, reusable IP, licenses, PDKs, board support, and canonical flows were queried and selected before custom infrastructure was authored.
  Evidence hint: research/TOOLCHAIN_CANDIDATES.md and research/IP_REUSE_PLAN.md

### rtl

- **rtl.contract-traceability** — Every synthesizable module and generated source traces to architecture/spec requirements and exactly matches the RTL manifest interfaces and parameters.
  Evidence hint: design/RTL_MANIFEST.json and RTL traceability notes

- **rtl.hardware-discipline** — RTL has intentional widths/signedness, complete combinational assignments, disciplined sequential logic, safe clock/reset/CDC behavior, bounded arrays/counters, and no unexplained latches, multiple drivers, or simulation-only design constructs.
  Evidence hint: lint/elaboration output and reviewer inspection

- **rtl.ip-provenance** — Third-party and generated IP have pinned source revisions, compatible licenses, wrappers, configuration, and regeneration commands.
  Evidence hint: design/RTL_MANIFEST.json provenance entries

### verification

- **verification.independent-oracle** — RTL outputs and state transitions are checked against an independent executable reference or formally specified properties, including numerical tolerances and quality constraints.
  Evidence hint: verification/PLAN.md, reference/, formal/, and verification/RESULTS.json; control profile uses CONTROL_PLAN.json and control/ASSESSMENT.json

- **verification.coverage-stress** — Unit/integration, reset, boundary, stalls/backpressure, illegal/error, randomized, CDC, X/Z, overflow, and representative workload cases meet declared coverage goals.
  Evidence hint: verification/RESULTS.json coverage and scenario summaries

- **verification.reproducible-green** — Fresh simulator/formal commands exit successfully, the referenced raw files exist, and passing summaries contain no contradictory failures. A control-profile diagnosis may retain real failures; control design/repair must pass both RTL and synthesized simulation.
  Evidence hint: verification/RESULTS.json and verification/raw/; control profile uses verification/control/ and the Engineer-authored verification/CONTROL_REVIEW.md

### ppa

- **ppa.constraints-and-provenance** — Target technology/device, tools, libraries/PDK, clocks, I/O constraints, memory treatment, parameters, corners, activity, and raw report paths are pinned.
  Evidence hint: ppa/PROTOCOL.md and ppa/RESULTS.json

- **ppa.timing-area-power** — Fresh timing/Fmax, area/resources including memory, power/energy methodology, utilization, warnings, and uncertainty are reported for the candidate and fair baselines.
  Evidence hint: ppa/RESULTS.json and ppa/raw/

- **ppa.physical-closure** — When physical design or GDS is claimed, placement/routing, congestion, STA, DRC, LVS, antenna, density, and generated-layout provenance satisfy the declared closure level.
  Evidence hint: ppa/RESULTS.json physical_closure and physical/raw/

- **ppa.incremental-area-reserve** — Every architecture frontier reports non-SRAM delta area/cells, Fmax, cycles, and remaining area reserve; repeated low-yield local tweaks stop and escalate to structural folding or an explicit Pareto characterization.
  Evidence hint: append-only PPA frontier ledger bound to RTL and constraint revisions

### prototype

- **prototype.delivery-level** — The declared FPGA, emulator, GDS, silicon, or structured N/A prototype level is consistent with the frozen chip scope and contains no broader hardware claim.
  Evidence hint: prototype/RESULTS.json

- **prototype.hardware-evidence** — Applicable prototype evidence records tool/board/chip identity, the build output, clocks and resources, host/runtime integration, on-hardware correctness, power, and raw commands/logs.
  Evidence hint: prototype/RESULTS.json and prototype/raw/

### benchmark

- **benchmark.protocol-fairness** — Candidate and baselines use identical workloads, quantization/quality, memory/host budgets, warmup, repetitions, synchronization, power method, and platform/technology constraints.
  Evidence hint: benchmark/PROTOCOL.md

- **benchmark.kernel-system-metrics** — Kernel and end-to-end results separately report latency/throughput, effective bandwidth and utilization, energy, area/resources, uncertainty, and workload-specific metrics.
  Evidence hint: benchmark/RESULTS.json and benchmark/raw/

- **benchmark.claim-boundary** — All regressions, unsupported cases, quality deltas, and market-reference limitations are explicit; different PDK nodes or commercial products are not presented as direct PPA wins.
  Evidence hint: benchmark/RESULTS.json limitations and comparison_scope

### signoff

- **signoff.artifact-integrity** — The final manifest links source, generated files, verification, PPA, prototype, benchmark, tool versions, git identity, and reproduction entry points.
  Evidence hint: signoff/ARTIFACT_MANIFEST.json and signoff/SIGNOFF.json

- **signoff.provenance-autonomy** — IP/license provenance, Argus role trajectories, intervention history, failed attempts, and independent Reviewer decisions support the stated autonomy claim.
  Evidence hint: signoff/SIGNOFF.json provenance and intervention records

- **signoff.bounded-result** — RESULTS.md is reproducible and limits claims to the certified delivery level, hardware, technology, workloads, quality, PPA, and benchmark evidence.
  Evidence hint: RESULTS.md and signoff/SIGNOFF.json

## Run the checks

Run from the project workspace; replace `<this folder>`, here and in every bundled guide, with this pack's absolute directory (the one holding this SKILL.md). Give every check the profile of the work: `--workflow-profile` (default `full`) and, for `custom`, `--workflow-stages` with the requested goals.

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' definition --project-root . --workflow-profile rtl
python3 '<this folder>/evidence.py' ppa --project-root . --workflow-profile custom --workflow-stages rtl ppa
python3 '<this folder>/environment_audit.py' catalog --category accelerator_ip
python3 '<this folder>/environment_audit.py' collect --project-root . --workflow-profile rtl
python3 '<this folder>/control.py' run --project-root .
python3 '<this folder>/control.py' summary --project-root .
python3 '<this folder>/control.py' reference <new directory>
```

`evidence.py <stage>` checks one of the nine stages above. Exit 0 prints `OK`; exit 1 prints one `FAIL:` line per issue, including a stage outside the profile; exit 2 means bad arguments. It reads:

- definition: `design/CHIP_SCOPE.json` (status `ready`, `delivery_level` one of `rtl_ip`, `fpga`, `gds`, `pre_tapeout`, `tapeout`, with target, workload, technology, interfaces, numerical formats, acceptance metrics, baselines and non-goals), plus non-empty `design/WORKLOAD.md` and `design/SPEC.md`.
- architecture: `design/MEMORY_MODEL.json`, `design/ARCHITECTURE.md` and `design/BASELINE_PLAN.md`.
- environment: `research/ENVIRONMENT_AUDIT.json` written by `environment_audit.py collect` under the same profile, with the tools probed again now, and a non-empty `design/TARGET.json`.
- rtl: `design/RTL_MANIFEST.json` and every source it lists.
- verification, ppa, prototype, benchmark: `<stage>/RESULTS.json` with a passing status (a prototype may instead be `not_applicable` with a reason unless the delivery level is `fpga`), existing raw files (verification also each command's `argv` and `exit_code: 0`, plus executable verification source under `tb/`, `testbench/`, `verification/`, `formal/` or `reference/`), and `source_copies`, which maps each consumed source (always the RTL manifest and its sources) to an independent copy made when the run consumed it. A source that no longer equals its copy makes the result stale. See the [verification contract](references/verification-contract.md).
- signoff (`full`, or `custom` with `signoff`): `signoff/SIGNOFF.json`, `RESULTS.md`, an artifact manifest listing every decisive file, and every earlier record again.
- `verification --workflow-profile control`: `verification/CONTROL_REVIEW.md`, then a replay of the whole native flow in a temporary directory (needs yosys, iverilog and vvp); see the [control contract](references/control-contract.md).

The exact fields are in [evidence.py](evidence.py). A passing check reads records; it does not show that the design is correct, the oracle independent or the claims true.

`environment_audit.py collect` writes `research/ENVIRONMENT_AUDIT.json` and `.md` for the delivery level in `design/CHIP_SCOPE.json` (pass `--target-python` for the project's interpreter): exit 0 when every required capability is ready, 1 when one is not, 2 when the scope is missing or a physical level names no supported PDK. `catalog` lists the curated tools and reusable IP (`--list-categories`, `--category`, `--platform`, `--query`).

`control.py run` executes the `apb4-timer-v1` study that `verification/CONTROL_PLAN.json` points to, into a new `verification/control/`: exit 0 when the result is accepted (a passing design, or a requested diagnosis with its failure retained), 1 otherwise, keeping the failing evidence. `summary` prints the JSON that `verification/CONTROL_REVIEW.md` must hold under `## Evidence`. `reference` builds and runs the packaged example ([control_reference.sv](control_reference.sv)) in a directory that must not exist.

The Engineer runs the check of each stage it hands to review and gives its output with the decisive raw files. The Reviewer reruns it when its tools include a shell; otherwise it judges from that output and the raw files, and never claims a run it did not make.

## Needs

Python 3.11+; the scripts use only the standard library and need no GPU. Simulation needs Verilator or Icarus Verilog (`iverilog` and `vvp`), lint needs Verilator, Verible or slang, synthesis needs Yosys, Vivado or Quartus, and FPGA, physical-design, sign-off, PDK and compiler/runtime needs follow the delivery level (`environment_audit.py` names the accepted tool bundles), together with any vendor licenses, boards and PDK access the target requires. `control.py` needs yosys, iverilog and vvp on PATH. Nothing is installed by this pack; `environment_audit.py` probes the machine only when a role runs it.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [chip-architecture-map.md](skills/engineer/chip-architecture-map.md)

- engineer: [chip-clock-reset-power.md](skills/engineer/chip-clock-reset-power.md)

- engineer: [chip-compute.md](skills/engineer/chip-compute.md)

- engineer: [chip-design-environment-first.md](skills/engineer/chip-design-environment-first.md)

- engineer: [chip-host-runtime.md](skills/engineer/chip-host-runtime.md)

- engineer: [chip-interconnect.md](skills/engineer/chip-interconnect.md)

- engineer: [chip-memory-dma.md](skills/engineer/chip-memory-dma.md)

- engineer: [chip-ppa.md](skills/engineer/chip-ppa.md)

- engineer: [chip-verification.md](skills/engineer/chip-verification.md)

- engineer: [digital-arbitration.md](skills/engineer/digital-arbitration.md)

- engineer: [digital-arithmetic.md](skills/engineer/digital-arithmetic.md)

- engineer: [digital-cdc-rdc.md](skills/engineer/digital-cdc-rdc.md)

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

- manager: [chip-scope-selection.md](skills/manager/chip-scope-selection.md)

- planner: [chip-scoped-planning.md](skills/planner/chip-scoped-planning.md)

- reviewer: [chip-design-signoff-review.md](skills/reviewer/chip-design-signoff-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [control.py](control.py)

- [control_reference.sv](control_reference.sv)

- [environment_audit.py](environment_audit.py)

- [evidence.py](evidence.py)

- [references/comparison-protocol.md](references/comparison-protocol.md)

- [references/control-contract.md](references/control-contract.md)

- [references/specialized_tool_registry.json](references/specialized_tool_registry.json)

- [references/tapeout-readiness.md](references/tapeout-readiness.md)

- [references/verification-contract.md](references/verification-contract.md)

- [references/workflow.md](references/workflow.md)
