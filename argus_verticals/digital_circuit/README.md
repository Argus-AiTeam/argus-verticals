# digital_circuit

**Purpose:** systematic digital-circuit knowledge and cycle-accurate RTL design,
verification and synthesis, from combinational logic through protocols and CDC.

New tasks select the smallest complete workflow: `specification`, `rtl`,
`verification`, `synthesis`, a dependency-checked `custom` combination, or explicit
`full`. Requesting `rtl + synthesis` includes specification and verification but
not delivery packaging. The full/legacy order remains
`specification → rtl → verification → synthesis → delivery`. Selected stages keep
their evidence checks; omitted stages do not require placeholder artifacts.
See the [knowledge and workflow map](skills/engineer/digital-knowledge-map.md)
for the twelve-topic library, RTL examples, pitfalls and verification methods.

The `benchmark/` subpackage remains a separate fixed-harness vertical
(`digital_circuit_benchmark`) that inherits this skill tree without changing its
benchmark contract.

During verification, the host runs the existing scoped completion checker and
supplies its result to the read/search-only Reviewer. The shared
[review contract](../hardware/shared/verification-review.md) distinguishes
numerical/RTL/physical claims and preserves project-specific precision and
continuation rules. This bridge does not replay project commands, strengthen
the legacy checker into an independent numerical oracle or migrate old tasks.

- `stages.py`: contract, checklists, completion checks (uses `argus.verticals.path_evidence`).
- `evidence.py`: fail-closed evidence checks (interface, preflight, verification sources) also consumed by `chip_design` and `benchmark/`.
- `skills/engineer/` (RTL verification, error-guided repair, spec-guidance registry, benchmark execution), `skills/reviewer/`.

Extras: none. Tests: `tests/skills/test_digital_circuit_vertical.py`, `tests/skills/test_digital_circuit_evidence.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).

Version 1.x requires Argus workflow composition (`VerticalContract.compose_workflow`).
Older frameworks reject the plugin visibly rather than silently running a
different flow. Upgrade the framework before this plugin; neither upgrading nor
installing it migrates existing task scope.
