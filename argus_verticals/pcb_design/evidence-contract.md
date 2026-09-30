# Canonical PCB evidence

Work only on the requested PCB scope. Specification needs `pcb/PLAN.json`;
design needs the selected native inputs and their local dependencies.
Verification needs the plan plus actual KiCad execution. Review additionally
needs `pcb/REVIEW.md`. No omitted stage is represented as a fake completed step.

The plan is a JSON object:

```json
{
  "objective": "Check the supplied board without redesigning it",
  "requirements": ["No native errors or warnings", "Exactly two plated holes"],
  "limitations": ["No physical fabrication, SI/PI or energizing claim"],
  "design": {
    "project": "design/coupon.kicad_pro",
    "schematic": "design/coupon.kicad_sch",
    "board": "design/coupon.kicad_pcb"
  },
  "checks": [
    {"kind": "erc", "max_errors": 0, "max_warnings": 0},
    {"kind": "drc", "max_errors": 0, "max_warnings": 0, "schematic_parity": true}
  ],
  "fabrication": {
    "layers": {"F.Cu": 3, "B.Cu": 2, "F.Mask": 2, "B.Mask": 2, "Edge.Cuts": 4},
    "drill_hits": {"pth": 2, "npth": 0}
  }
}
```

The numeric values above describe the bundled original coupon, **not generic
limits**. Derive requirements and feature/hole counts from the actual task and
design before execution. `requirements` and `limitations` are distinct nonempty
string lists. Error/warning bounds and feature/hole counts are nonnegative
integers. Do not increase bounds or change sources merely to obtain acceptance.
An explicitly requested diagnostic study may retain nonzero error/warning
bounds; report those findings instead of describing the design as clean.

`checks` may contain ERC only, DRC only, both or neither. DRC explicitly selects
`schematic_parity: true|false`; true requires the matching root schematic.
`fabrication` may be omitted/null for checking only. At least one check or
fabrication export is required for verification. Fabrication alone does not
imply ERC, DRC or parity passed. Export every enabled copper layer and Edge.Cuts;
request additional mask, paste and legend layers explicitly. Each layer maps
to its minimum count of drawn Gerber D01/D03 features, not a component count.
Drill counts are exact round-hole hits, separately PTH and NPTH; zero is valid.
All paths are project-relative. Board/root schematic must share the project's
directory and basename so native KiCad reads the intended settings.

## Supported native inputs

Install `kicad-cli` **9.x** and the provider's `sexpdata` Python dependency.
Native KiCad executes the checks; the parser only resolves inputs and structure.
Use modern `.kicad_pro`, `.kicad_sch`, `.kicad_pcb`, optional `.kicad_dru`,
project-local `sym-lib-table`/`fp-lib-table`, `.kicad_sym` and `.pretty` libraries.
Referenced symbols/footprints must resolve through those local tables, not a
user installation. Library URIs may use `${KIPRJMOD}`; other variables, parent
escapes, remote/absolute dependencies, custom drawing sheets, nonempty library
options, project text variables, excluded findings and explicitly disabled
check severities are unsupported. Hierarchical local sheets are followed
recursively, including cyclic-reference rejection. Only the selected schematic
or board and actual referenced footprint files are required; symbol libraries
are retained in full. The local tables themselves are always retained.

This initial planar backend accepts nonempty boards with at least two pads, a
named net and Edge.Cuts geometry. It supports enabled multilayer copper,
round PTH/NPTH pads and full-through vias. Board copper zones require explicit
`zone_refill: true` as described below. Rule areas, footprint-local zones,
multi-layer zone objects, blind/microvias, slots and routed drills remain
unsupported. No hidden refill or source rewrite is performed.
Three-dimensional models are not used or validated by these
planar checks/exports. At most 64 distinct schematic sheets, 256 input files,
32 MiB per parsed file and 128 MiB total are accepted. Unsupported inputs must
be reported, not simplified behind the user's back.

## Explicit copper-zone refill

Set the top-level `zone_refill` boolean to `true` for a selected board operation
when the board contains copper zones. Omitting it or setting it false rejects
zones rather than trusting previously saved polygons. ERC alone does not need
or permit refill; refill does not imply DRC or fabrication was selected.
Up to 256 board-level zones with distinct original KiCad identities are supported.
Each must have original polygon outlines and one enabled copper layer. Separate
single-layer zones may cover every layer of a multilayer board.

KiCad 9 CLI has no refill command. This mode also requires the official
`pcbnew` Python module with **exactly the same version** as `kicad-cli`.
The runner invokes `/usr/bin/python3 -I` by default; `ARGUS_KICAD_PYTHON` may
explicitly select the matching KiCad interpreter on another installation.
Do not install an unrelated PyPI package named pcbnew into Argus. Missing
bindings, a version mismatch or failed native fill is a retained failure,
not permission to fall back to stale copper. The old zone-free mode does not
need these bindings.

Original project files and `pcb/results/inputs` stay byte-identical. Refill
runs on another complete selected input copy under `pcb/results/native/work`,
retaining the project's basename, adjacent settings, local libraries and rules.
Every selected command, including DRC and manufacturing export, uses that
same working project. Its board is the **refilled export source**, not a
replacement for the user's original.

The helper discards all stored fills, runs native `ZONE_FILLER`, and saves
the working board. Native serialization without fills must agree before and
after filling, so a change to non-fill design data fails. Native formatting
may differ from the original; original bytes are still retained separately.
Malformed custom rules must fail explicitly: the helper initializes them
through native `WriteDRCReport` because `LoadBoard` alone suppresses parse
errors. `refill-rules.rpt`, when present, is a pre-fill diagnostic, **not**
the selected post-fill DRC result or an additional acceptance requirement.

`refill.json` records the native operation/version, original zone identities,
names, nets, layers and filled polygon area in mm2. `refill-unfilled.kicad_pcb`
records native non-fill serialization; the final board remains under `work`.
These outputs are retained and independently regenerated. Empty fill is
reported as zero area, not a fabricated plane. Positive area does not establish
connectivity, minimum required area, impedance or return-path adequacy; examine
the requested post-fill DRC and original engineering requirements. Polygon
area is not copper volume and does not substitute for the separate drill files.

## Execution and acceptance

The runner refuses an existing `pcb/results`. It copies the exact input closure
under `pcb/results/inputs`, isolates KiCad configuration, executes the selected
commands, and retains native JSON, console logs, Gerber X2 and Excellon output.
Gerbers use millimetres, 4.6 coordinates, absolute origin and explicit layers;
drills use millimetres, decimal coordinates and separate PTH/NPTH files.
No global/user KiCad settings are an intended input. The project rules still
need engineering review: default/native rule coverage is not universal.

`pcb/results/RESULTS.json` is written by the runner, not invented manually.
It identifies `operation: "kicad-cli"` (or `"kicad-cli+pcbnew"` with refill),
actual `kicad_version`, execution status,
input/output copy maps and ordered command rows (`kind`, exact `command`,
`cwd`, `exit_code`, `log`). Native exit 5 means violations, not tool success
with zero findings. DRC includes its ordinary violations, unconnected items
and, when requested, schematic parity findings. Exclusions always fail.
Failed commands and rejected bounds retain their records and outputs.

The checker verifies current independent copies, report identities/severities,
original bounds, expected filenames, nonempty requested geometry and exact
hole counts. It then re-executes KiCad on a separate temporary input copy and
compares reports and fabrication contents. Only known generation timestamps
and unstable report item UUIDs are omitted from this comparison; coordinates,
descriptions, severities and manufacturing geometry are not normalized away.
It does not modify the project. Native version changes require a fresh run.
With refill it also repeats the fill from the original input copy and compares
the full saved working-board bytes and zone measurements, not just matching
copies or a report saying that filling succeeded.

Successful ERC/DRC establishes only the checks actually enabled in the retained
project and supported native tool. File generation is not fab acceptance,
electrical correctness, SI/PI analysis, assembly verification, compliance,
physical testing or permission to energize hardware. State unperformed work.
