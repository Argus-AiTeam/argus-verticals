---
name: pcb_design
description: "PCB and printed circuit board engineering: schematics, components and footprints, stackup, placement, routing, return paths and fabrication preparation; executable KiCad copper-zone refill on copies, ERC/DRC, schematic-board parity, Gerber and Excellon drill outputs; not RTL, IC layout, RF network calculation, package design, field-solved SI/PI or physical qualification"
version: 0.3.0
---

# pcb_design

PCB and printed circuit board engineering with native KiCad 9 checks and fabrication exports, from requirements through schematic/board work to an independently reviewed, bounded conclusion.

## What counts as done

### specification

- **pcb.requirements** — Interfaces, constraints, acceptance limits and exclusions are explicit.
  Evidence hint: pcb/PLAN.json

### design

- **pcb.inputs** — Selected native designs and project-local dependencies are nonempty and explicit.
  Evidence hint: pcb/PLAN.json and actual KiCad project

### verification

- **pcb.native-results** — Native reports and manufacturing geometry agree with independent execution and original bounds.
  Evidence hint: pcb/results/RESULTS.json and native outputs

### review

- **pcb.conclusion** — The conclusion separates native checks and file generation from fabrication suitability and physical validation.
  Evidence hint: pcb/REVIEW.md and current evidence

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' check --project-root . --stage specification
python3 '<this folder>/evidence.py' check --project-root . --stage design
python3 '<this folder>/evidence.py' run --project-root .
python3 '<this folder>/evidence.py' check --project-root . --stage verification
python3 '<this folder>/evidence.py' check --project-root . --stage review
python3 '<this folder>/evidence.py' reference <new directory> [--zones]
```

Write `pcb/PLAN.json` exactly as [evidence-contract.md](evidence-contract.md) describes; it is the authoritative plan schema, supported KiCad subset and acceptance rule. Do only the stages the task asks for; review needs the verification it reviews, not unrelated stages.

- `check --stage specification`: the plan has a nonempty `objective` and distinct nonempty `requirements` and `limitations`.
- `check --stage design`: the plan's project, root schematic and/or board resolve, with their project-local libraries and rules, into a closed input set inside the supported subset.
- `run` (Engineer): copies that input closure to `pcb/results/inputs`, runs only the selected refill, ERC, DRC, Gerber and drill commands with isolated KiCad settings, writes `pcb/results/RESULTS.json`, logs and retained outputs, then runs the verification check. It refuses an existing `pcb/results`; move a previous attempt aside rather than deleting it.
- `check --stage verification`: the recorded run is complete, input and output copies match current files, reports stay within the plan's error/warning bounds, Gerber feature and drill hit counts match, and a fresh KiCad replay on a temporary copy reproduces the reports and fabrication files. It does not modify the project. `review` additionally needs a nonempty `pcb/REVIEW.md`.
- `reference`: builds the bundled original two-testpoint coupon (with `--zones`, the four-layer coupon whose zones are refilled on a copy) in a directory that must not exist yet, then runs it; use it to confirm this machine's KiCad toolchain.

Exit 0 prints any measured counts and an OK/PASS line; exit 1 prints `FAIL: <reason>` (a `run` that got as far as creating `pcb/results` also records `status: failed` and the error in RESULTS.json). RESULTS.json records absolute commands and paths, so check from the same project location `run` used, and if a zone refill used `--kicad-python`, pass the same value to `check`. Exit 0 confirms only the selected recorded checks and exports; it is not Reviewer approval, fabrication suitability or physical qualification. Missing KiCad, a missing or mismatched `pcbnew`, or an unsupported design is a failure, never a pass. Do not invent RESULTS.json, suppress findings, raise bounds after a failure, refill or rewrite source boards, or equate a successful export with fabrication approval.

## Needs

Python 3.10+ with `sexpdata>=1.0.2,<2` to read KiCad files (`--help` and the specification check use only the standard library). `run`, `reference` and the verification/review checks need KiCad 9.x with `kicad-cli` on PATH; boards with copper zones (`zone_refill: true`) also need KiCad's official `pcbnew` Python binding at exactly the same version, in its own interpreter (default `/usr/bin/python3`, or an absolute path given with `--kicad-python`). No GPU, license or network access is needed; fabrication, assembly, SI/PI field solving and physical testing are outside this pack. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [pcb-assembly.md](skills/engineer/pcb-assembly.md)

- engineer: [pcb-components.md](skills/engineer/pcb-components.md)

- engineer: [pcb-knowledge-map.md](skills/engineer/pcb-knowledge-map.md)

- engineer: [pcb-layout.md](skills/engineer/pcb-layout.md)

- engineer: [pcb-manufacturing.md](skills/engineer/pcb-manufacturing.md)

- engineer: [pcb-native-execution.md](skills/engineer/pcb-native-execution.md)

- engineer: [pcb-power-thermal.md](skills/engineer/pcb-power-thermal.md)

- engineer: [pcb-schematic.md](skills/engineer/pcb-schematic.md)

- engineer: [pcb-signal-integrity.md](skills/engineer/pcb-signal-integrity.md)

- engineer: [pcb-stackup.md](skills/engineer/pcb-stackup.md)

- manager: [pcb-decisions.md](skills/manager/pcb-decisions.md)

- planner: [pcb-planning.md](skills/planner/pcb-planning.md)

- reviewer: [pcb-review.md](skills/reviewer/pcb-review.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence.py](evidence.py)

- [evidence-contract.md](evidence-contract.md)

- [refill.py](refill.py): zone refill helper that `run`, `reference` and the verification check invoke with KiCad's Python

- [references/coupon/](references/coupon/coupon.kicad_pro): original two-testpoint coupon project used by `reference` (`coupon.kicad_pro`, `coupon.kicad_sch`, `coupon.kicad_pcb`, `local.kicad_sym`, `local.pretty/Probe.kicad_mod`, `sym-lib-table`, `fp-lib-table`)

- [references/four-layer-zones.kicad_pcb](references/four-layer-zones.kicad_pcb): four-layer zone board used by `reference --zones`
