# Chip Design Vertical Workflow

The explicit `full` profile, and legacy projects with no saved profile, use:

```text
definition
→ architecture
→ environment
→ rtl
→ verification
→ ppa
→ prototype
→ benchmark
→ signoff
```

## Delivery levels

| Level | Minimum certified result |
| --- | --- |
| `rtl_ip` | synthesizable RTL, independent verification, synthesis/PPA, benchmark |
| `fpga` | RTL IP requirements plus implemented bitstream and on-board evidence |
| `gds` | RTL IP requirements plus physical design and STA/DRC/LVS closure |
| `tapeout` | GDS requirements plus antenna, IO/package, and the foundry's tapeout submission checks |

Within `full`, stages remain present for every level. `prototype/RESULTS.json` may use
`not_applicable` only when the scope does not require physical prototype evidence.

## Scoped tasks

New tasks default to the smallest complete named workflow matching the requested
outcome. The Manager must select `WORKFLOW_PROFILE`; the framework persists both
its name and required stage order. It does not edit global provider stages.

| Profile | Stages |
| --- | --- |
| `architecture` | definition, architecture |
| `rtl` | definition, architecture, environment, rtl, verification |
| `verification` | verification |
| `ppa` | verification, ppa |
| `prototype` | verification, ppa, prototype |
| `benchmark` | verification, ppa, benchmark |
| `full` | all nine stages |

An omitted stage is outside scope, not skipped/accepted evidence. Its files are
not required. Selected stages retain their existing checks and independent
review; existing-design profiles need valid current inputs. Changing profiles
requires a new operator-authorized handoff. No existing project is auto-migrated.

Delivery level describes the target, not a claim that all work toward it was
completed. An architecture study targeting FPGA remains an architecture result.
Explicit complete IP/GDS/pre-tapeout/tapeout delivery uses `full`; physical
requirements are not weakened by scoped profiles.

The `rtl` environment profile requires simulation and lint. Use
`environment_audit collect|check --workflow-profile rtl`; default CLI behavior
remains the full delivery-level environment audit. Tool availability is probed
again during acceptance, and a report for the wrong profile is rejected.

## Project layout

```text
design/
research/
rtl/ or src/
verification/
formal/
ppa/
physical/
prototype/
benchmark/
signoff/
RESULTS.md
```

Raw outputs belong below their owning stage and must not masquerade as source.
