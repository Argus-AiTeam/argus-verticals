---
name: physics
description: "theory, simulation, data analysis, literature, or experiment design for a real physical system with bounded evidence"
version: 0.2.0
---

# physics

theory, simulation, data analysis, literature, or experiment design for a real physical system with bounded evidence.

Let the physical question choose theory, simulation, data, literature, or experiment work. Keep units, assumptions, evidence, and claim boundaries honest. No fixed table, file count, or process output proves scientific value.

## How the work goes

The work goes through scope → model → execute → review → manuscript, reusing settled evidence from an earlier phase instead of redoing it. The phases are coarse: derivation, simulation, data analysis, literature synthesis, and experiment design are methods chosen for the task, not mandatory steps. The work is finished when the Reviewer accepts the paper and the manuscript check in "Run the checks" exits 0.

**Scope focus.** Define the physical system, regime, observables, and success criterion. Search current primary literature far enough to identify the closest work and a real separation; use whatever notes make that judgment clear, not a fixed matrix or paper count.

**Model focus.** State variables, units, equations or data sources, assumptions, validity ranges, and boundary/initial conditions. Choose theory tools because the problem needs them, not to fill a capability inventory.

**Execute focus.** Produce claim-bearing derivation, computation, data analysis, or experiment evidence. Use convergence, scans, controls, and uncertainty in proportion to the claim. Treat weak or negative feedback as a reason to repair or change the route, not as a paper conclusion.

**Review focus.** Independently judge physical correctness, novelty against current closest work, significance, and the evidence boundary of each claim. Replan when the central idea is too weak; do not convert uncertainty into paperwork.

**Manuscript focus.** Write a conventional paper around one central physical insight. Use claim-driven figures, real citations, reproducible methods, and concise limitations. The Reviewer judges venue quality from the paper itself; no fixed figure count, exact ledger schema, or internal-process narrative proves readiness.

## What counts as done

### scope

- **scope.faithful-goal** — The original physics goal is stated faithfully, with the physical system, its domain/regime, and the observables of interest explicit.
  Evidence hint: a faithful task statement naming the system, domain, and observables

- **scope.task-type-success** — The task type and success criterion are explicit: derive, simulate, analyze data, synthesize literature, design an experiment, estimate, or make bounded progress — with an honest criterion for completion.
  Evidence hint: a declared task type and an honest, checkable success criterion

- **scope.dynamic-route** — A feasible route is chosen from the physical structure of the task: theoretical derivation, numerical simulation, data analysis, literature synthesis, experiment design, or a bounded negative result — not a forced, fixed sequence of methods.
  Evidence hint: a task-specific route with reasons for included and skipped methods

### model

- **model.variables-equations** — Variables, parameters, units, and the governing equations, model, or data sources are explicit and internally consistent.
  Evidence hint: a variable/parameter table with units and the equations or data sources

- **model.assumptions-bcic** — Assumptions, the validity range of each approximation, and the boundary and initial conditions are stated explicitly.
  Evidence hint: listed assumptions, approximation ranges, and BC/IC

- **model.validation-target** — The observables and the validation target are declared: an analytic limit, a baseline, a residual, convergence, an uncertainty budget, or an explicit evidence boundary.
  Evidence hint: a named validation target the execute stage can be checked against

### execute

- **execute.bounded-evidence** — The execute work produced real, bounded evidence — a derivation, a computation, a data analysis, a literature synthesis, or a feasibility judgment — rather than an unsupported assertion.
  Evidence hint: explicit derivations, reproducible runs, analyzed data, or cited synthesis

- **execute.provenance** — Every numerical, data, and literature claim carries provenance: the source, the code/run, or the reference it came from.
  Evidence hint: run logs, dataset ids, or resolvable citations for each claim

- **execute.no-overclaim** — Finite simulation or toy data is not presented as a proof of a universal or infinite physical statement; the tested regime and the evidentiary limit are stated.
  Evidence hint: the tested range plus the precise limit of what it supports

- **execute.honest-boundary** — When a critical condition is missing (data, apparatus, or full-text literature), the work names the missing condition plainly or returns a clearly bounded surrogate instead of pretending to be complete.
  Evidence hint: a note naming the missing condition, or the bounded surrogate used in its place

### review

- **review.no-system-drift** — There is no physical-system drift: the reviewed work still concerns the original system, regime, and observables.
  Evidence hint: a comparison of the reviewed result against the original scoped system

- **review.no-workflow-drift** — There is no agent-workflow or meta-paper drift and no toy-overclaim: the result is about the physics, not about the workflow that produced it.
  Evidence hint: confirmation that claims are physical, not workflow byproducts or metadata

- **review.units-bcic** — Units and dimensions are checked where they apply, and boundary and initial conditions are checked where they apply.
  Evidence hint: a dimensional-consistency and BC/IC check, or a reason it does not apply

- **review.evidence-boundary** — The numerical, data, and literature evidence boundary is explicit, and metadata-only sources are not treated as full text.
  Evidence hint: labeled evidence levels: full-text, excerpt, code/data, metadata-only, unavailable

- **review.claim-status** — Every final claim is labeled supported, partial, inconclusive, or unknown, with the remaining gaps stated.
  Evidence hint: claim-by-claim status labels and stated remaining gaps

### manuscript

- **manuscript.compiled-paper** — What the stage delivers is a conventional research paper, not a scope/model/execute/review log, and MANUSCRIPT.tex compiles to a current MANUSCRIPT.pdf.
  Evidence hint: a current compiled MANUSCRIPT.pdf and its MANUSCRIPT.tex source

- **manuscript.scientific-quality** — The paper communicates the physical result with evidence, citations, methods, figures or tables where they help, and explicit limitations in proportion to the claims it makes.
  Evidence hint: Reviewer assessment of the paper's claim-to-evidence fit and reproducibility

- **manuscript.no-overclaim** — No claim over-extends its evidence: finite numerics are not universal proofs, synthetic/toy results are not real-system validation, and novelty/discovery claims are bound to evidence or downgraded.
  Evidence hint: an evidence-bounded claim set with no finite->universal or synthetic->real leap

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/manuscript.py' --help
python3 '<this folder>/manuscript.py' check --project-root .
```

The check covers the deterministic part of **manuscript.compiled-paper**: project-root `MANUSCRIPT.tex` is non-empty, `MANUSCRIPT.pdf` is non-empty and begins with `%PDF-`, and the PDF is not older than the `.tex`. It does not build the paper; compile `MANUSCRIPT.tex` first, then run the check. Exit 0 prints `manuscript stage: compiled paper is ready`; exit 1 lists each failure on stderr. A passing check says nothing about the paper's content: every other item above, including scientific quality and overclaiming, is the Reviewer's judgment from the work itself.

## Needs

Python 3.10+; manuscript.py uses only the standard library, needs no third-party package and no GPU. Building `MANUSCRIPT.pdf` needs a LaTeX distribution such as TeX Live (`pdflatex` or `latexmk`). The physics work itself needs whatever the chosen route demands: solvers or numerical libraries, compute, datasets, full-text literature access, and for experiment work the apparatus and authorization to use it. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file.

- planner: [physics-research-planning.md](skills/planner/physics-research-planning.md)

- engineer: [physics-research-execution.md](skills/engineer/physics-research-execution.md)

- reviewer: [physics-research-review.md](skills/reviewer/physics-research-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [manuscript.py](manuscript.py)
