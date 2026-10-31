---
name: package_design
description: "Semiconductor package engineering: die attach, wire bond, flip chip and bumps, package substrates, interposers, chiplets, thermal paths, mechanical and assembly constraints; executable Gmsh/CalculiX steady thermal studies of ideal bonded stacks with fixed-temperature or prescribed convection boundaries; not PCB fabrication, RTL, RF network calculation, general structural FEA or physical qualification"
version: 0.3.0
---

# package_design

Semiconductor package engineering knowledge, with genuine Gmsh/CalculiX steady thermal studies of ideal bonded package stacks.

## What counts as done

### specification

- **package.requirements** — Interfaces, numerical conditions and unsupported physical claims are explicit.
  Evidence hint: package/PLAN.json

### model

- **package.models** — Geometry, material sources, SI units and ideal-interface assumptions are explicit.
  Evidence hint: package/PLAN.json and declared model files

### thermal

- **package.native-results** — Native mesh and temperature/heat fields match current inputs, original bounds and declared refinement comparisons.
  Evidence hint: package/results/RESULTS.json and native solver files

### review

- **package.conclusion** — The conclusion distinguishes model heat conduction from package reliability, manufacturing and measured behavior.
  Evidence hint: package/REVIEW.md and current evidence

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' check --project-root . --stage specification
python3 '<this folder>/evidence.py' check --project-root . --stage model
python3 '<this folder>/run_analysis.py' .
python3 '<this folder>/evidence.py' check --project-root . --stage thermal
python3 '<this folder>/evidence.py' check --project-root . --stage review
python3 '<this folder>/reference.py' <new directory> [--convection]
```

Write `package/PLAN.json` and the model files it declares exactly as [evidence-contract.md](evidence-contract.md) specifies: it is the canonical schema, metric table and list of what is not modelled. Work only on the stages the task asks for; review needs current thermal evidence, the other stages stand alone.

`evidence.py check` never changes the project. `specification` checks the plan's objective, requirements and limitations; `model` also every declared model file. `thermal` checks the whole plan, then `package/results/RESULTS.json`: tool versions, input and output copies, command records and exit codes, mesh volumes, interfaces and boundary areas, steady-step fields, heat balance within 1e-5, every check within its original bounds and every coarse/fine comparison; it then re-executes Gmsh and CalculiX in a temporary directory and compares each saved native file. `review` also needs a nonempty `package/REVIEW.md`. Exit 0 prints `no issues`; exit 1 prints each issue as `ERROR: ...`. No issues means model consistency and the stated numerical bounds, not Reviewer approval or physical package qualification.

`run_analysis.py <project>` is the Engineer's runner: it copies the plan and selected models to `package/results/inputs`, runs Gmsh then CalculiX for each run in `package/results/native/<run id>/` (one thread, 180 s and 32 MiB of console per command), keeps retained copies, writes `RESULTS.json` and runs the thermal check. Exit 0 prints the measured metrics and `PASS: ...`; exit 1 prints `FAIL: <reason>`, and a failure once execution has started leaves `RESULTS.json` with `status: failed` beside the partial logs. It refuses an existing `package/results`: before an intentional rerun move the old one aside (for example to `package/attempts/<n>/`), never delete it.

`reference.py <new directory>` writes an original ideal reference project and runs it: a slab with R=t/(kA)=1 K/W, a two-layer stack with 1.5 K/W and a mesh-refined die-on-substrate spreading pair; `--convection` runs six convection studies instead (bottom-cooled slab 11 K/W, top-cooled 10 K/W, every exposed face cooled). Run it on a new machine or tool version before trusting project results; exit codes as for `run_analysis.py`.

Do not invent native files, loosen limits to pass, infer material properties from a package label, or claim thermal, stress or reliability coverage beyond the actual model. Missing tools or an exceeded execution limit leave the work incomplete; they are neither a pass nor a valid negative result.

## Needs

Python 3.10+. `evidence.py` for the specification and model stages uses only the standard library; the thermal and review checks, `run_analysis.py` and `reference.py` also need numpy>=1.26 and, on PATH, Gmsh 4.x >= 4.12 (`gmsh`) and CalculiX 2.x >= 2.21 (`ccx`). Gmsh 4.12.1 and CalculiX 2.21 are the validated versions (Ubuntu 24.04: `apt-get install gmsh calculix-ccx`). Both are open source; no commercial EDA tool, license, GPU or physical lab is used. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [package-advanced-integration.md](skills/engineer/package-advanced-integration.md)

- engineer: [package-architecture.md](skills/engineer/package-architecture.md)

- engineer: [package-assembly.md](skills/engineer/package-assembly.md)

- engineer: [package-die-attach.md](skills/engineer/package-die-attach.md)

- engineer: [package-interconnect.md](skills/engineer/package-interconnect.md)

- engineer: [package-knowledge-map.md](skills/engineer/package-knowledge-map.md)

- engineer: [package-mechanics.md](skills/engineer/package-mechanics.md)

- engineer: [package-native-execution.md](skills/engineer/package-native-execution.md)

- engineer: [package-substrates.md](skills/engineer/package-substrates.md)

- engineer: [package-thermal.md](skills/engineer/package-thermal.md)

- manager: [package-decisions.md](skills/manager/package-decisions.md)

- planner: [package-planning.md](skills/planner/package-planning.md)

- reviewer: [package-review.md](skills/reviewer/package-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence-contract.md](evidence-contract.md): plan and model schema, metrics, refinement rules and exclusions

- [evidence.py](evidence.py)

- [run_analysis.py](run_analysis.py)

- [reference.py](reference.py)

- [model.py](model.py), [mesh.py](mesh.py), [native.py](native.py): modules the scripts import
