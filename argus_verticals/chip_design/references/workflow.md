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
| `pre_tapeout` | GDS requirements plus executable digital verification, equivalence, DFT and physical-readiness checks; no submission or fabrication claim |
| `tapeout` | GDS requirements plus antenna, IO/package, and the foundry's tapeout submission checks |

Within `full`, stages remain present for every level. `prototype/RESULTS.json` may use
`not_applicable` only when the scope does not require physical prototype evidence.

## Scoped tasks

New tasks default to the smallest complete preset or composed workflow matching the requested
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

## Dependency-aware composition

If no preset fits, choose `WORKFLOW_PROFILE=custom` with requested goals, for
example `WORKFLOW_STAGES=rtl;ppa`. The host adds the transitive closure of:

| Requested stage | Required companions |
| --- | --- |
| definition | none |
| architecture | definition |
| environment | none |
| rtl | architecture, environment, verification |
| verification | none; existing RTL/manifest/oracle must be valid |
| ppa | verification |
| prototype | ppa |
| benchmark | ppa |
| signoff | all earlier stages |

Companions are obligations, not execution edges: RTL requires later verification.
The effective sequence always follows the original canonical order. For example:

- `rtl + ppa`: definition, architecture, environment, rtl, verification, ppa.
- `architecture + ppa`: definition, architecture, verification, ppa; existing
  RTL is an input, not an implementation task.
- `prototype + benchmark`: verification, ppa, prototype, benchmark on existing RTL.
- `environment`: audit tools/PDK/IP for the declared target, without creating RTL.
- `signoff`: complete full coverage, not a shortened certification route.

The Manager explains requested, automatically included and excluded work.
Pipeline state records both requested goals and effective stages. Continuation
cannot alter either silently; dependency changes that alter the saved order
also require a new handoff. Presets and legacy scope remain unchanged.
This is not an arbitrary reordering or parallel DAG scheduler.

For custom environment evidence, both collection and checking use the actual
scope, e.g. `--workflow-profile custom --workflow-stages rtl ppa`. Custom
RTL/verification-only execution requires simulation/lint, whereas PPA and later
implementation/measurement work retain target-level capabilities. The report's
effective stages must match the saved scope and tools are freshly probed.
An architecture-only composition needs no execution toolchain; an environment-only
audit still checks the declared target's full tool readiness.

## Why full remains useful, and how to iterate

The nine milestones cover the questions a complete delivery must answer:
what and why, architecture feasibility, executable environment, traceable RTL,
independent correctness, implementation cost, target demonstration, fair workload
measurement, and reproducible final claims. They are acceptance boundaries, not
a requirement to start every file from zero or delay all verification until RTL
is finished. Check tool feasibility early and design the oracle before coding;
the later environment/verification stages establish their accepted evidence.

Use the same target contract throughout. For `rtl_ip`, synthesis/PPA and
benchmark evidence can be simulation-based with explicit limitations; prototype
N/A is allowed only by the existing target rules. FPGA needs implemented board
evidence. Physical levels require physical closure and their additional
readiness evidence. A target-level final review is not fabricated-silicon proof.
If benchmark or final packaging is not requested, select a custom task rather
than weakening `full`.

Architecture, RTL and PPA often require feedback. Run bounded experiments,
verify every changed candidate and compare under matched constraints. Repair
within the active task using existing review/repair mechanisms; do not
silently replace its deliverable. A new handoff can open a different scope.
Accepted upstream artifacts may be reused after checking freshness, but the
selected stages still need review and completion. Source/interface/constraint/
target changes invalidate affected downstream evidence; scope selection does
not itself provide general dependency-based artifact invalidation.

Keep goals, evidence and claims separate: an architecture proposal, verified
RTL, measured PPA and complete delivery are all useful outcomes, but none
automatically implies the next. Missing existing inputs block a short workflow
rather than licensing fabricated reports or automatic scope expansion.

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
