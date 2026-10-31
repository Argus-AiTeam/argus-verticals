---
name: analog_mixed_signal
description: "analog/mixed-signal circuits: bias, small-signal gain, feedback, op-amps, filters, noise, device models and data-converter interfaces; executable ngspice operating-point, DC sweep, AC and transient analysis with parameter corners, margins and numerical refinement, not RTL verification, RF/EM, PCB layout or foundry sign-off"
version: 0.3.0
---

# analog_mixed_signal

analog/mixed-signal circuits: bias, small-signal gain, feedback, op-amps, filters, noise, device models and data-converter interfaces; executable ngspice operating-point, DC sweep, AC and transient analysis with parameter corners, margins and numerical refinement, not RTL verification, RF/EM, PCB layout or foundry sign-off.

## What counts as done

### specification

- **analog.requirements** — Observable analog requirements and exclusions are explicit.
  Evidence hint: analog/PLAN.json

### model

- **analog.models** — Actual circuit/model inputs have named provenance, validity and limitations.
  Evidence hint: analog/PLAN.json models and project-local SPICE files

### simulation

- **analog.native-analysis** — Requested native analyses are current; envelope coverage and refinements are valid, with fixed-goal diagnosis/design acceptance.
  Evidence hint: analog/results/RESULTS.json, native waveforms and optional ASSESSMENT.json

### review

- **analog.conclusion** — The conclusion distinguishes ideal/model-dependent simulation from measured or manufactured behavior.
  Evidence hint: analog/REVIEW.md and current simulation evidence

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' check --project-root . --stage specification
python3 '<this folder>/evidence.py' check --project-root . --stage model
python3 '<this folder>/evidence.py' run --project-root .
python3 '<this folder>/evidence.py' check --project-root . --stage simulation
python3 '<this folder>/evidence.py' check --project-root . --stage review
```

Write `analog/PLAN.json` as the [evidence contract](evidence-contract.md) describes: either per-run `runs` with numerical checks, or a `robustness` operating-envelope study. `check` is read-only on the project. `specification` needs the objective, identified requirements and limitations; `model` also needs each listed model or deck file to exist with kind, source, validity and limitations (an envelope plan's operating specification and includes must resolve too); `simulation` requires unchanged independent input/output copies under `analog/results/` and recomputes every measurement from the native waveforms against its declared bounds; for an envelope study it replays every case with ngspice in a temporary directory (`TMPDIR` must be writable; its records hold the project's absolute path and the ngspice version, so check in place with the ngspice `run` used) and requires `task_accepted` in a matching `ASSESSMENT.json`; `review` also needs `analog/REVIEW.md`. Exit 0 prints `OK` and means the stage's record checks passed, not that the physical circuit is qualified; exit 1 prints each issue as `ERROR:`.

`run` validates the plan, needs ngspice on `PATH`, refuses an existing `analog/results`, freezes input copies, runs each declared analysis (an envelope study: every scenario at coarse and fine resolution) and writes `RESULTS.json` (and `ASSESSMENT.json`). Exit 0 prints the measurements or assessment and `PASS`; exit 1 prints `FAIL:` and the reason (missing ngspice, invalid plan, ngspice failure, a measurement outside its bounds, a rejected design study) and keeps the partial native output. A fixed `diagnose` goal can pass with out-of-limit findings recorded in the assessment; a `design` goal cannot.

Two references each create a new directory, run ngspice, and show a complete plan:

```sh
python3 '<this folder>/evidence.py' reference <new directory>
python3 '<this folder>/evidence.py' envelope-reference <new directory> [--goal diagnose] [--tight]
```

`reference` runs six analyses (RC operating point, DC transfer, AC and step response; finite-gain one-pole amplifier operating point and AC) against `fc=1/(2*pi*R*C)`, `tau=R*C`, `Acl=A0/(1+A0*beta)` and `fcl=fp*(1+A0*beta)` with R=1 kohm, C=100 nF, A0=100000, fp=10 Hz, beta=1/11. `envelope-reference` studies a loaded RC network and a Shockley diode at 17 conditions with all four analysis kinds: the default design passes, `--goal diagnose --tight` is an accepted negative diagnosis, and `--tight` alone exits 1.

Explain missing inputs or tools and failed bounds explicitly; never manufacture waveforms, loosen acceptance to obtain a pass, or forge result records. Consistent records do not prove authentic execution, adequate models, sufficient numerical resolution or physical safety; review these independently.

## Needs

Python 3.10+; evidence.py uses only the standard library and needs no GPU. `run`, both references and the `simulation`/`review` checks of an envelope study (which replay every case) need native ngspice 42 or newer on `PATH` (for example `apt install ngspice`); the other checks only read files. No license, PDK, vendor model or lab hardware is used, and nothing is energized. This pack installs nothing.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [analog-amplifiers.md](skills/engineer/analog-amplifiers.md)

- engineer: [analog-bias-small-signal.md](skills/engineer/analog-bias-small-signal.md)

- engineer: [analog-converters-interfaces.md](skills/engineer/analog-converters-interfaces.md)

- engineer: [analog-feedback-stability.md](skills/engineer/analog-feedback-stability.md)

- engineer: [analog-filters-transients.md](skills/engineer/analog-filters-transients.md)

- engineer: [analog-knowledge-map.md](skills/engineer/analog-knowledge-map.md)

- engineer: [analog-models-corners.md](skills/engineer/analog-models-corners.md)

- engineer: [analog-ngspice-evidence.md](skills/engineer/analog-ngspice-evidence.md)

- engineer: [analog-noise-dynamic-range.md](skills/engineer/analog-noise-dynamic-range.md)

- engineer: [analog-passives-physical.md](skills/engineer/analog-passives-physical.md)

- manager: [analog-scope-selection.md](skills/manager/analog-scope-selection.md)

- planner: [analog-analysis-planning.md](skills/planner/analog-analysis-planning.md)

- reviewer: [analog-independent-review.md](skills/reviewer/analog-independent-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence.py](evidence.py)

- [evidence-contract.md](evidence-contract.md): the plan, result and operating-envelope formats every role works to

- [reference/amplifier.inc](reference/amplifier.inc), [reference/amplifier_ac.cir](reference/amplifier_ac.cir), [reference/amplifier_op.cir](reference/amplifier_op.cir): one-pole feedback amplifier decks used by `evidence.py reference`

- [reference/rc.inc](reference/rc.inc), [reference/rc_ac.cir](reference/rc_ac.cir), [reference/rc_dc.cir](reference/rc_dc.cir), [reference/rc_op.cir](reference/rc_op.cir), [reference/rc_tran.cir](reference/rc_tran.cir): ideal RC decks used by `evidence.py reference`
