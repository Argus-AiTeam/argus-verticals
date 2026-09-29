# PCB design

Independent `hardware / pcb_design` domain. Knowledge spans requirements,
schematics, component selection, footprints, stackup, placement, routing,
returns, power/thermal reasoning, manufacturing and assembly preparation.
It does not inherit digital, analog, RF or package workflows.
`vertical.json` declares its Store identity, Python dependency and shared
hardware file-record helpers; classification is not workflow inheritance.

Profiles are `specification`, `design`, `verification`, `review` and optional
`full`. Existing-project checks and fabrication-only requests are first-class;
review requires only the selected verification, not every design stage.
The canonical [evidence contract](evidence-contract.md) is inserted in all
four real role prompts.

## Native execution

Install KiCad **9.x** with `kicad-cli` and `pip install 'argus-verticals[pcb]'`.
KiCad's Python board API is **not** a runtime dependency. The original reference
was generated once with KiCad's native board writer; its schematic, footprint
and symbol are original package data, not copied vendor/library examples.

```bash
python -m argus_verticals.pcb_design.run_reference /tmp/original-pcb-reference
python -m argus_verticals.pcb_design.run_analysis /path/to/prepared-project
```

The reference has two matching testpoints, a routed named net, a 20 x 10 mm
outline and two 1 mm plated holes. It executes ERC, DRC with schematic parity,
five Gerber layers and separate PTH/NPTH drill files. The checker independently
replays native operations, not just JSON counts or filename existence.
Failures are retained; a results directory is never silently overwritten.

The first executable subset is deliberately narrower than PCB knowledge:
modern project-local libraries/settings, local hierarchical sheets, planar
boards with round through holes and full-through vias. Copper zones/rule areas,
slots, blind/microvias, external libraries, suppressed findings and custom
drawing sheets are unsupported. See the contract for file limits, explicit
operation selection and initial manufacturing conventions.

Native checks do not prove design intent, universal DFM, SI/PI, thermal limits,
assembly yield, physical performance or regulatory compliance. This provider
does not send designs to a manufacturer or energize hardware.

## Sources

- [KiCad 9 CLI manual](https://docs.kicad.org/9.0/en/cli/cli.html): command semantics and native exit codes.
- [KiCad PCB Editor manual](https://docs.kicad.org/9.0/en/pcbnew/pcbnew.html): stackup, rules and manufacturing output.
- [KiCad Schematic Editor manual](https://docs.kicad.org/9.0/en/eeschema/eeschema.html): symbols, connectivity and ERC.
- [KiCad file-format reference](https://dev-docs.kicad.org/en/file-formats/): native S-expression structures.

Knowledge notes describe engineering reasoning, not substitutes for material,
component, manufacturer, connector or applicable regulatory specifications.
