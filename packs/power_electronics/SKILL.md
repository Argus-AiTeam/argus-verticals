---
name: power_electronics
description: "Power electronics: DC-DC converters, power switches and rectifiers, magnetics, control and protection, losses, filters and layout constraints; native ngspice Buck/Boost startup, ripple, load-step and finite operating/tolerance studies with margins; not general analog signal processing, PCB fabrication, RF networks or physical energizing"
version: 0.3.0
---

# power_electronics

Power electronics: DC-DC converters, power switches and rectifiers, magnetics, control and protection, losses, filters and layout constraints; native ngspice Buck/Boost startup, ripple, load-step and finite operating/tolerance studies with margins; not general analog signal processing, PCB fabrication, RF networks or physical energizing.

## What counts as done

### specification

- **power.requirements** — Operating conditions, observation windows and original numerical limits are explicit.
  Evidence hint: power/PLAN.json

### model

- **power.models** — Topology, component sources, units and unsupported device behavior are explicit.
  Evidence hint: power/PLAN.json and declared models

### simulation

- **power.native-results** — Native evidence satisfies the fixed task goal: complete valid diagnosis, or a design meeting all limits and margins.
  Evidence hint: power/results/RESULTS.json, native files and any declared operating-envelope assessment

### review

- **power.conclusion** — The conclusion distinguishes modeled waveforms from device ratings, real efficiency, hardware safety and physical qualification.
  Evidence hint: power/REVIEW.md and current results

## Run the checks

Every role reads [evidence-contract.md](evidence-contract.md) first: it is the exact schema for `power/PLAN.json`, model JSON, operating specifications, metrics, windows and limits. Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' check --project-root . --stage specification
python3 '<this folder>/evidence.py' check --project-root . --stage model
python3 '<this folder>/run_analysis.py' .
python3 '<this folder>/evidence.py' check --project-root . --stage simulation
python3 '<this folder>/evidence.py' check --project-root . --stage review
```

`evidence.py check` prints the stage's issues as a JSON list: `[]` with exit 0 means the stage passed, exit 1 prints the first issue. `specification` validates the plan's objective, requirements and limitations (in envelope mode it also resolves the whole declared operating study); `model` also validates every declared model file against the contract's bounds; in single-condition mode neither checks `runs` or `convergence`, which `run_analysis.py` validates before it creates `power/results`; `simulation` checks the results record, unchanged independent copies of inputs and native files, the ngspice version, native completion, every original limit, energy balance and steady windows, re-runs ngspice in temporary directories and requires identical waveforms, then checks sample growth and time-step deltas; in envelope mode it also requires full coverage, a saved `power/results/ASSESSMENT.json` equal to the recomputation, and task acceptance. `review` is `simulation` plus a nonempty `power/REVIEW.md`. Each simulation/review check replays ngspice again; an envelope may take minutes.

`run_analysis.py` (Engineer) validates the whole plan, refuses an existing `power/results`, runs every study through ngspice, retains native files with independent copies and writes `power/results/RESULTS.json` (plus `ASSESSMENT.json` for an envelope), then replays and checks the result as the simulation check does. Exit 0 prints the measurements (or the assessment); exit 1 prints `error: ...` and leaves the failed attempt in place. Before an intentional rerun, move `power/results` aside and keep it. Results record absolute paths, so check the project where it ran. A completed diagnosis can exit 0 with `ASSESSMENT.status: "failed"` and `task_accepted: true`; a design that misses any limit or margin exits 1 with "operating-envelope task not accepted".

Worked references, each creating and running a new project directory: `python3 '<this folder>/run_reference.py' <new dir>` (Buck and Boost startup, load doubling and steady windows, bounds from independent averaged CCM equations, coarse/fine steps) and `python3 '<this folder>/run_robustness_reference.py' <new dir> [--goal diagnose|design] [--tight]` (Buck supply × capacitance envelope: the default design passes; `--goal diagnose --tight` completes with failed engineering status; `--tight` alone exits 1). Use them to confirm ngspice works and as plan templates.

`[]` and exit 0 establish bounded numerical agreement for an illustrative model, not hardware safety, device qualification or measured efficiency, and are not Reviewer approval. Missing ngspice, failed replay or an exhausted time budget is a failure, not a pass. Do not invent waveforms, relax original bounds after seeing results, replace switching analysis with averaged equations, or infer safe hardware operation.

## Needs

Python 3.10+; the scripts use only the standard library and need no GPU. Simulation, review and the runners need native ngspice 42 or newer on PATH (`ngspice -n --version`); the specification and model checks need no simulator. No license, device library or hardware is used, and physical energizing is out of scope. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [power-capacitors-filters.md](skills/engineer/power-capacitors-filters.md)

- engineer: [power-control-compensation.md](skills/engineer/power-control-compensation.md)

- engineer: [power-converter-topologies.md](skills/engineer/power-converter-topologies.md)

- engineer: [power-emi-layout.md](skills/engineer/power-emi-layout.md)

- engineer: [power-inverters-drives.md](skills/engineer/power-inverters-drives.md)

- engineer: [power-isolated-conversion.md](skills/engineer/power-isolated-conversion.md)

- engineer: [power-knowledge-map.md](skills/engineer/power-knowledge-map.md)

- engineer: [power-losses-thermal.md](skills/engineer/power-losses-thermal.md)

- engineer: [power-magnetics.md](skills/engineer/power-magnetics.md)

- engineer: [power-native-execution.md](skills/engineer/power-native-execution.md)

- engineer: [power-operating-envelope.md](skills/engineer/power-operating-envelope.md)

- engineer: [power-protection-startup.md](skills/engineer/power-protection-startup.md)

- engineer: [power-semiconductors-drivers.md](skills/engineer/power-semiconductors-drivers.md)

- manager: [power-decisions.md](skills/manager/power-decisions.md)

- planner: [power-planning.md](skills/planner/power-planning.md)

- reviewer: [power-review.md](skills/reviewer/power-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence-contract.md](evidence-contract.md)

- [evidence.py](evidence.py)

- [run_analysis.py](run_analysis.py)

- [run_reference.py](run_reference.py)

- [run_robustness_reference.py](run_robustness_reference.py)

- Imported by the scripts: [model.py](model.py), [native.py](native.py), [robustness.py](robustness.py), [shared.py](shared.py), [study.py](study.py), [waveform.py](waveform.py)
