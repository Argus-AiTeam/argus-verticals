---
name: materials
description: "materials science and materials processing across atomistic, microstructure, continuum, CAD/CAE, and experimental scales"
version: 0.2.0
---

# materials

materials science and materials processing across atomistic, microstructure, continuum, CAD/CAE, and experimental scales.

## What counts as done

### scope

- **scope.material-system** — The material composition, phase or microstructure, processing or service state, relevant environment, and observables are explicit.
  Evidence hint: the actual material system, state, environment, and measured outputs

- **scope.scale-regime** — The relevant spatial and temporal scales and physical regime are identified, so an electronic, atomistic, mesoscale, continuum, process, data-driven, or experimental route can be chosen for physical reasons.
  Evidence hint: a justified scale/regime choice and the phenomena it retains or omits

- **scope.success-criterion** — Success is checkable and matches the request: explanation, calibrated model, property prediction, validated process design, reproduced result, new finding, or an honest bounded negative result.
  Evidence hint: a task-specific observable, comparator, tolerance, or decision criterion

- **scope.physical-safety** — If the route includes physical synthesis, processing, testing, or instrument operation, the authorized personnel, approved procedure, hazards, interlocks, required controls, and waste handling are established before execution; simulation-only work marks this item not applicable.
  Evidence hint: applicable laboratory/process authorization and controls, or a simulation-only rationale

### grounding

- **grounding.primary-sources** — Claims about prior materials, mechanisms, models, and measurements are grounded in resolvable primary sources or authoritative databases at the evidence level actually available.
  Evidence hint: primary papers, standards, database records, or public datasets read directly

- **grounding.baseline-gap** — The strongest relevant baseline and closest prior work are identified, and any novelty or improvement claim states the exact difference rather than relying on a generic literature gap.
  Evidence hint: a direct comparison with the strongest applicable prior result

- **grounding.data-tools-access** — Data provenance, licenses, material-property sources, solver availability, compute, and experimental access are checked before the plan depends on them.
  Evidence hint: real access evidence and explicit constraints for data, software, compute, and lab equipment

### model

- **model.physics-and-units** — The governing physics, variables, equations, units, parameter sources, assumptions, and validity range are explicit and dimensionally consistent.
  Evidence hint: the implemented model and parameter values with units and provenance

- **model.material-state** — Material behavior reflects the relevant composition, phase, temperature, strain rate, texture, defects, microstructure, and processing history rather than an unjustified generic material card.
  Evidence hint: material-state inputs and the evidence supporting each important dependency

- **model.discretization-boundaries** — Geometry, periodic cell or CAD model, discretization, interactions or contact, boundary/initial conditions, loads, ensembles, and solver controls match the physical question.
  Evidence hint: actual model inputs plus an explanation of the chosen boundaries and discretization

- **model.calibration-validation-split** — Parameters fitted or selected from data are separated from validation evidence; the evaluation does not reuse its target as an input or tune on hidden answers.
  Evidence hint: a declared calibration/selection set and an independent validation set or oracle

### execute

- **execute.real-run** — The claimed calculation or experiment actually ran. Generated scripts, input decks, GUI screenshots, or submitted jobs alone are not solver or instrument results.
  Evidence hint: native outputs, logs, job identity, timestamps, and parsed observables from a completed run

- **execute.reproducible-provenance** — Inputs, structures or CAD, material parameters, pseudopotentials or force fields, mesh, software and versions, seeds, hardware, commands, and output files are preserved to the level needed to reproduce the claim.
  Evidence hint: the exact executable path, versioned inputs, run command, environment, and native outputs

- **execute.health-failures** — Solver or experiment health is inspected during execution; divergence, non-convergence, unstable dynamics, distorted elements, unphysical states, instrument faults, and failed attempts remain visible and are not relabeled as data.
  Evidence hint: diagnostics and retained failure evidence alongside accepted runs

- **execute.capability-boundary** — Unavailable licenses, software, hardware, samples, or instruments produce an explicit statement of what is missing or a clearly labeled surrogate, never a fabricated run.
  Evidence hint: real capability discovery and an honest boundary for anything not run

- **execute.physical-safety-compliance** — Any physical experiment or processing run stayed within its authorization, approved procedure, equipment interlocks, and material-handling and disposal controls; non-physical work states that this is not applicable.
  Evidence hint: run-specific authorization and safety records, or a non-physical execution rationale

### validate

- **validate.numerical-convergence** — Numerical claims are supported by convergence or stability checks appropriate to the method: mesh/time step/cell size, k-points/cutoff, sampling duration, optimizer tolerance, or another justified control.
  Evidence hint: fresh convergence or stability results over the parameters that can change the conclusion

- **validate.physical-consistency** — Units, conservation laws, symmetries, limiting cases, monotonic trends, bounds, and known physical behavior are checked where applicable.
  Evidence hint: independent physical sanity checks tied to the actual observables

- **validate.independent-reference** — Headline results are compared like-for-like against an independent analytic result, public benchmark, trusted implementation, published measurement, or new physical experiment under matching conditions.
  Evidence hint: raw comparison data with matched material state, geometry, conditions, and metric

- **validate.sensitivity-uncertainty** — Important parameter, model-form, stochastic, and measurement uncertainties are tested or bounded, and conclusions are no stronger than their robustness.
  Evidence hint: sensitivity or uncertainty results for the assumptions that could reverse the claim

- **validate.integrity** — The evaluation is independent of optimization and protected against leakage, hard-coded known outputs, edited references, selective run deletion, and comparison across mismatched hardware, conditions, or metrics.
  Evidence hint: a frozen evaluator or protocol plus complete raw attempts and like-for-like baselines

### report

- **report.claim-evidence** — Every main claim points to actual calculations, raw data, figures, tables, literature, or experimental records, and the evidence supports its stated scope.
  Evidence hint: claim-by-claim traceability to inspectable evidence

- **report.simulation-experiment-boundary** — Predicted, simulated, surrogate, and experimentally measured quantities are distinguished explicitly; a digital result is not described as physical validation.
  Evidence hint: clear labels for each evidence type and any missing real-world validation

- **report.reproducibility-limitations** — The delivered result records reproduction instructions, material and process conditions, software or instrument details, uncertainty, negative results, known limitations, and the domain where the conclusion applies.
  Evidence hint: a proportional report or paper plus runnable inputs and retained raw evidence

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' check --project-root . --stage execute
python3 '<this folder>/evidence.py' check --project-root . --stage validate
python3 '<this folder>/evidence.py' check --project-root . --stage report
```

Create project `research/MATERIALS_EVIDENCE.json` with `version: 1` and a non-empty `evidence` list of `{kind, path}` entries. Paths must be unique, project-relative, contained, existing non-empty files. The allowed kinds and per-check requirements are in [evidence.py](evidence.py). `execute` needs native output, run log, analysis, experimental record, or blocker; `validate` needs validation or blocker; `report` needs report plus both preceding groups. Exit 0 confirms a structurally valid index; exit 1 prints each issue. A blocker can document a bounded negative result; neither a passing index nor job completion proves scientific success. Inspect native evidence and the checks above independently.

## Needs

Python 3.10+; evidence.py uses only the standard library and needs no GPU. Scientific execution needs task-selected data, solver or instrument access, licenses and hardware, and authorization for physical work. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [materials-atomistic-simulation.md](skills/engineer/materials-atomistic-simulation.md)

- engineer: [materials-cad-cae-process-simulation.md](skills/engineer/materials-cad-cae-process-simulation.md)

- engineer: [materials-data-literature-grounding.md](skills/engineer/materials-data-literature-grounding.md)

- engineer: [materials-ecosystem-routing.md](skills/engineer/materials-ecosystem-routing.md)

- engineer: [materials-experiment-loop.md](skills/engineer/materials-experiment-loop.md)

- engineer: [materials-research-execution.md](skills/engineer/materials-research-execution.md)

- manager: [materials-research-manager.md](skills/manager/materials-research-manager.md)

- planner: [materials-research-planning.md](skills/planner/materials-research-planning.md)

- reviewer: [materials-research-review.md](skills/reviewer/materials-research-review.md)

- reviewer: [materials-simulation-signoff.md](skills/reviewer/materials-simulation-signoff.md)

- reviewer: [materials-validation-review.md](skills/reviewer/materials-validation-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence.py](evidence.py)
