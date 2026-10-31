---
name: rf_design
description: "RF and microwave network design: Touchstone/S parameters, impedance matching, transmission lines, port order and reference impedances, passive cascades, noise and stability reasoning; executable scikit-rf network analysis and finite component-tolerance/frequency robustness, not RTL, general SPICE transients, full-wave EM, PCB layout or physical certification"
version: 0.3.0
---

# rf_design

RF and microwave network design: Touchstone/S parameters, impedance matching, transmission lines, port order and reference impedances, passive cascades, noise and stability reasoning; executable scikit-rf network analysis and finite component-tolerance/frequency robustness, not RTL, general SPICE transients, full-wave EM, PCB layout or physical certification.

## What counts as done

### specification

- **rf.requirements** — Observables, physical assumptions and exclusions are explicit.
  Evidence hint: rf/PLAN.json

### model

- **rf.models** — Network sources, port conventions, frequency grids and model limits are defined.
  Evidence hint: rf/PLAN.json and actual Touchstone inputs

### analysis

- **rf.network-results** — Current exported networks agree with the declared calculations and task goal: design meets original limits; diagnosis may validly report failures.
  Evidence hint: rf/results/RESULTS.json, retained Touchstone results and selected robustness assessment

### review

- **rf.conclusion** — The conclusion distinguishes sampled network calculations from calibration, full-wave and measured hardware claims.
  Evidence hint: rf/REVIEW.md and current analysis evidence

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' run --project-root .
python3 '<this folder>/evidence.py' check --project-root . --stage analysis
python3 '<this folder>/evidence.py' inspect --project-root .
python3 '<this folder>/reference.py' <new directory> [--robustness]
```

Work only on the selected stages and requested networks. Write `rf/PLAN.json`, and for a tolerance study its external specification, exactly as [evidence-contract.md](evidence-contract.md) defines; it also gives port order, units, metrics and limits.

`run` calculates the declared studies with scikit-rf from copies under `rf/results/inputs`, retains Touchstone results, writes `rf/results/RESULTS.json` (and `ASSESSMENT.json` for a tolerance study), and refuses an existing `rf/results`: preserve prior results before an intentional rerun. Exit 0 prints the measurements and PASS (ACCEPTED for a tolerance study); exit 1 prints FAIL and the reason, keeping the failed record.

`check --stage specification|model|analysis|review` is read-only and prints the issue list. `specification` checks the plan's objective, requirements and limitations; `model` also builds every declared network; `analysis` recomputes every exported network and measurement from the current inputs; `review` is `analysis` plus a nonempty `rf/REVIEW.md`. `[]` and exit 0 mean the declared task goal was accepted, not physical certification; exit 1 means the evidence is incomplete or a bound failed.

In a tolerance study, read `ASSESSMENT.json`: a diagnosis may validly report failed original limits, while a design must pass every original check and required margin. `inspect` (tolerance studies only, read-only) recomputes the complete assessment even when the design was not accepted: exit 0 means the saved assessment and run status match it and prints `task_accepted`; exit 1 means they differ or the run is incomplete.

`reference.py` writes a new project with independently known answers and runs it: matched 0.5 attenuator S21 -6.0206 dB, its cascade -12.0412 dB, series 50 ohm S11 1/3 and S21 2/3, the same renormalized to 75 ohms 1/4 and 3/4, quarter-wave line S21 -j, 50-to-100 ohm L-match zero reflection, unit transmission and -45 degrees; `--robustness` checks that L-match across all +/-5 percent L/C combinations plus nominal on two grids. Exit 0 confirms the installed toolchain reproduces them; both projects are worked examples of the plan formats.

Engineer executes the declared calculations; Reviewer independently checks the reference planes, models, conventions and numerical comparisons; Manager and Planner preserve the original acceptance conditions. Explain failed bounds or unavailable methods explicitly. Do not invent measured data, clip bad values, relax requirements to pass, or forge completion records.

## Needs

Python 3.10+ with numpy>=1.26 and scikit-rf>=2.1,<3 (which brings scipy and pandas) for evidence.py; reference.py uses only the standard library but runs evidence.py with the same interpreter. Calculations run in-process on the CPU and need no GPU, EM or SPICE solver, license, VNA or other hardware; measured claims need the task's own Touchstone data and its provenance. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [rf-knowledge-map.md](skills/engineer/rf-knowledge-map.md)

- engineer: [rf-network-execution.md](skills/engineer/rf-network-execution.md)

- engineer: [rf-waves-ports.md](skills/engineer/rf-waves-ports.md)

- engineer: [rf-transmission-lines.md](skills/engineer/rf-transmission-lines.md)

- engineer: [rf-matching.md](skills/engineer/rf-matching.md)

- engineer: [rf-filters.md](skills/engineer/rf-filters.md)

- engineer: [rf-active-noise.md](skills/engineer/rf-active-noise.md)

- engineer: [rf-stability-passivity.md](skills/engineer/rf-stability-passivity.md)

- engineer: [rf-measurement.md](skills/engineer/rf-measurement.md)

- engineer: [rf-physical.md](skills/engineer/rf-physical.md)

- manager: [rf-scope-selection.md](skills/manager/rf-scope-selection.md)

- planner: [rf-study-planning.md](skills/planner/rf-study-planning.md)

- reviewer: [rf-independent-review.md](skills/reviewer/rf-independent-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence-contract.md](evidence-contract.md) — the plan, network, metric and retained-result contract

- [evidence.py](evidence.py) — runner and read-only checker

- [reference.py](reference.py) — reference projects with known answers
