# Contributing

Thanks for adding to Argus's verticals. English and Chinese are both fine, in
code comments, Skill markdown, issues and pull requests alike.

## Ground rules

1. **One vertical per directory.** `argus_verticals/<name>/` owns its
   `stages.py`, helpers, `skills/`, `README.md`, and nothing else's. A nested
   sub-vertical (like `digital_circuit/benchmark`) is registered under the
   joined name (`digital_circuit_benchmark`).
2. **No cross-vertical imports**, except through a documented shared helper
   package such as `argus_verticals/literary/shared/`, or an explicit,
   README-documented dependency on a parent vertical (as `chip_design` uses
   `digital_circuit.evidence`). Framework code is imported from `argus`;
   never copy framework modules into a vertical.
3. **Absolute imports across packages.** Inside a vertical, relative imports
   are fine; anything that crosses a vertical boundary is written as
   `from argus_verticals.<name>...` or `from argus...`.
4. **No secrets, no data dumps.** No API keys, tokens, or credentials in code,
   tests, fixtures, or Skill markdown. Fixtures are small hand-written samples;
   corpora, market data, model weights and benchmark dumps stay out of the
   repository and are documented as external inputs.
5. **Tests are required.** Every deterministic check a vertical ships (evidence
   validators, prosody checks, patch engines, CLIs) has a test under `tests/`.
   Tests that need optional heavy dependencies skip when they are absent
   (`pytest.importorskip`, or a guarded import that skips).
6. **The conformance test is the gate.** `tests/test_contract_conformance.py`
   imports every entry point, checks `ARGUS_VERTICAL_API_VERSION`,
   `VERTICAL_PURPOSE`, `VERTICAL_SKILLS`, `VERTICAL_SKILL_PARENTS`, runs Argus's
   own `vertical_contract` validation, and requires a `README.md` and an
   entry-point registration for every directory with a `stages.py`. A pull
   request whose vertical fails it is not reviewed further.
7. **Keep the voice.** `tests/test_voice_wordlist.py` keeps the moved files'
   model- and operator-visible prose free of Argus's retired machinery words.
   When you rewrite a file's prose to that standard, add it to
   `VOICE_CLEAN_FILES`; never remove a file to silence a failure.
8. **Purpose lines route tasks.** `VERTICAL_PURPOSE` is what the Manager reads
   to choose a vertical. Keep it to one line, name what the vertical is, and,
   where a neighbour exists, what it is not. Changing an existing purpose is a
   behaviour change: say so in the pull request.
9. **Every vertical carries a `vertical.json`, and its version moves with its
   directory.** The manifest (schema: `catalog/vertical.schema.json`) is what
   the Argus Vertical Store installs from. Bump the vertical's `version`
   (semver) in the same pull request that changes any file under its `paths`:
   patch for fixes and prose, minor for new checks or skills, major when the
   stage order or a deliverable changes. Keep `requires` and `shared` equal to
   what the code imports (`tests/test_catalog.py` checks this against the
   actual imports and `VERTICAL_SKILL_PARENTS`), and keep the English purpose
   out of the manifest: it lives in `stages.py` only. Regenerate the index with
   `python scripts/build_catalog.py`; CI fails on a stale `catalog.json`.
   Releases are repository-wide tags `vX.Y.Z`: pushing one builds and attaches
   `<name>-<version>.zip` for every vertical, so a vertical whose version did
   not change ships a byte-identical archive.

## Ownership

Semantic ownership per vertical is optional and lives in `.github/CODEOWNERS`
when a maintainer wants review requests routed to them. Absence of an owner
does not block a change; the conformance test and a reviewer do.

## Workflow

Install Argus first, at or after the 2026-09-14 split (the commit that made
vertical discovery dynamic and added `VERTICAL_SKILL_PARENTS`); an older Argus
ignores skill parents and still lists the 17 verticals as built-ins, and the
conformance test says so. The same day's package rename is required too: the
Python package `argus_skill` became `argus` and the pip distribution
`argus-skill` became `argus`; this package imports `argus` and registers the
`argus.verticals` entry-point group, and the conformance test fails against an
older Argus with "Argus is older than the argus_skill → argus rename; update
Argus". (`ARGUS_SKILL_*` environment variables and `~/.argus-skill` kept their
spelling.) This package declares no pip dependency on Argus because Argus is
not on PyPI.

The hardware 1.x verticals additionally require composable workflow profiles
(`VerticalContract.compose_workflow`). The verification specialty and FPGA domain
also require `VerticalPlugin.routing_path`, as does the analog/mixed-signal
domain; `.github/workflows/tests.yml` pins the merged framework revision from
lbx154/Argus#172. Upgrade Argus before
those plugins; legacy projects keep their saved workflow. Hardware example tests
use Icarus Verilog (`iverilog` and `vvp`); the iCE40 implementation tests also
use Yosys, nextpnr-ice40 and IceStorm (`icepack`). CI installs these tools so
documented RTL and native implementation are executed, not only linted.
Analog references additionally require `ngspice`, also installed in CI. They
execute native operating-point, DC, AC and transient analyses and compare
waveform measurements against independent circuit equations. Keep parser-only
fixtures distinct from genuine simulator output and test altered physical
parameters against unchanged acceptance bounds.
`WORKFLOW_STAGE_REQUIREMENTS` describes companion obligations for custom scopes,
not a reordered execution graph. Preserve preset/full orders, validate reused
inputs, and test closure and evidence for each new combination. These changes are
part of the hardware 1.0.0 upgrade released in repository release v0.2.0.

Hardware expansion uses `VERTICAL_ROUTING_PATH`, for example
`("hardware", "digital_circuit", "benchmark")`. Domain and optional specialty
must join to the entry-point name. The generator owns `routing_path` in the
catalog: do not duplicate it in `vertical.json`. Classification, explicit skill
parents, and independent workflow contracts are separate. Skill parents are
direct, not recursive, and existing parent-first duplicate precedence remains.
Do not create a vertical for every circuit primitive; use topic skills unless
the specialty owns an independently requested result and acceptance method.
Generic hardware record helpers live in `argus_verticals/hardware/shared/`.
Declare that path in each importing provider's manifest `shared` list; it is
not a skill parent or an executable provider. Keep legacy verification helper
imports compatible for existing FPGA callers.

```bash
pip install "argus @ git+https://github.com/lbx154/Argus.git@main"
pip install -e ".[dev,zh-fold]"
ruff check argus_verticals tests scripts
python scripts/build_catalog.py --check
pytest -q
```

Open a pull request against `main`. Describe what the vertical does, what it
deliberately does not do, and how you tested it. Small, focused pull requests
are reviewed fastest.

## Compatibility with Argus

Argus's version number does not track the split, so compatibility is probed,
not declared: `tests/test_contract_conformance.py` requires
`VerticalPlugin.skill_parents` to exist in the installed Argus and
`argus.verticals._registry.ENTRY_POINT_GROUP` to be `"argus.verticals"`, the
group this package registers (an Argus from before the rename has no `argus`
module at all, and the test says so before anything else). When Argus bumps
`VERTICAL_API_VERSION`, this package follows with a release that updates every
`ARGUS_VERTICAL_API_VERSION`; until then Argus ignores the mismatched plugins
and logs why, so a stale install fails loudly rather than silently.
