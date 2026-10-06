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
domain; `.github/workflows/tests.yml` pins the exact framework revision including
hardware routing and concrete Manager decision targets. The latter prevents a
literal prompt placeholder from turning an explicit completion into an invalid
target. Upgrade Argus before those plugins; legacy projects keep their saved
workflow. Hardware example tests
use Icarus Verilog (`iverilog` and `vvp`); the iCE40 implementation tests also
use Yosys, nextpnr-ice40 and IceStorm (`icepack`). CI installs these tools so
documented RTL and native implementation are executed, not only linted.
Bounded chip-control tests use Yosys and Icarus for both RTL and synthesized
simulation against the original APB4 peripheral contract. Cover all byte
strobes, exact waits, unmapped/RO errors, timer boundaries, set-dominant W1C,
IRQ masks and asynchronous reset during traffic. Mutate actual RTL and require
both models to expose defects; verify inclusive original generic-cell caps,
fresh native replay and Store-only profile acceptance. Preserve authorized
repair diffs and failed attempts; never claim physical PPA from generic cells.
Final control acceptance also checks the Engineer report and its exact measured
summary. Test missing/contradictory reports and that malformed reports fail before
native replay. Verify event-count and cycle-witness recomputation, completed
strobe coverage, and rejection of idle frames carrying impressive case labels.
Exercise the registered host round-evidence hook in a fresh Store process,
including read-only Reviewer prompts, explicit failures and isolation from
legacy profiles; native checks must not depend on Reviewer shell permissions.
Coverage is based on independent reference conditions, so faulty DUT responses
remain diagnosable; absent stimulus coverage never qualifies as a diagnosis.
General digital/chip verification and the FPGA checker use the same existing
Argus host round-evidence API. Test the saved scoped contract against a separate
execution directory, custom prerequisites, visible failures, and the absence of
recorded-command replay or project/state mutation. Control keeps its dedicated
native report check, without a second generic replay. These changes require that
framework API; they do not activate or migrate historical project runtimes.
Keep the hardware manifests' `argus_features` declarations aligned with those
real dependencies. The feature-aware Store must refuse an unsupported selected
dependency before changing installed files, preserve old installed versions
when only a catalog update is incompatible, and expose the cause to operators.
`min_argus` is informational; an older Store ignoring the new field is not an
enforcement boundary. Do not automatically upgrade frozen project runtimes.
CI pins the feature-aware Store implementation through `ARGUS_REF` in
`.github/workflows/tests.yml`. The release-catalog test checks the actual Store
parser and feature refusal against the current manifests; fresh Store-only
native cases also require the declarations to survive installation.
The framework's existing Linux suite separately consumes a fixed provider
checkout through `ARGUS_VERTICALS_REPO`, without pip-installing these providers.
Keep both CI references explicit when changing this contract. They are test
inputs, not runtime migration instructions or scientific acceptance receipts.
For general simulation/formal, test explicitly declared `supporting_files`
(precision contracts, oracle dependencies and retained fixtures) for independent
current copies and invalid paths. Binding inputs does not establish oracle
independence or substitute for a project's scientific acceptance.
Chip's legacy verification format uses its existing `source_hashes`, not the
specialty's copies. Test all declared entries, duplicate/malformed bindings,
original numerical contracts and evaluator/helper changes. An optional
`verification/PLAN.json` and every `supporting_files` entry must be bound.
Exercise the same failures through host review and final completion, without
executing recorded commands. Preserve valid legacy records, exact numerical
variant selection, integer command exits and finite unambiguous JSON.
The opt-in digital CDC/reset tests use native Yosys extraction and Icarus traces,
including bad stage counts, intermediate fanout, wrong clocks, asynchronous
release and raw-reset paths that digital simulation alone may miss. Keep the
legacy full verification workflow unchanged; CDC-only work has an explicit
profile and original specification. Preserve failing design evidence and valid
negative diagnoses, test fresh native replay and Store-only profile checking,
and do not claim metastability/MTBF or complete CDC/RDC sign-off.
CDC follow-up tests must show that swapped independently declared data inputs
produce trace mismatches, not just structural failures, and that detailed native
findings survive recomputation. Check live output-budget enforcement, terminated
command exits and owned process cleanup; never weaken a threshold to pass.
The shared native process monitor serves CDC, chip control, SPICE and
PCB/package command execution. Preserve each caller's original time/output
limits, native exits and diagnostics. Test observation exceptions and a parent
that exits while its child still runs; cleanup must target only owned process
POSIX groups. PCB/package consoles stream to disk with a live 32 MiB stop threshold,
not an unbounded memory capture. Numerical acceptance is separate from these
execution budgets.
The five independent analog/RF/PCB/package/power workflows also supply scoped
host evidence to read-only Reviewers. Cover all declared stages and actual
native results, project immutability and unchanged task selection. Existing
analog/power proof copies may be written only in separate runtime state.
Exercise both original and extended studies in fresh Store-only processes;
shared-helper source changes must invalidate reused numerical validation.
When changing a shared directory, bump every manifest that bundles it so an
unchanged provider version never silently receives different archive bytes.
Analog references additionally require `ngspice`, also installed in CI. They
execute native operating-point, DC, AC and transient analyses and compare
waveform measurements against independent circuit equations. Keep parser-only
fixtures distinct from genuine simulator output and test altered physical
parameters against unchanged acceptance bounds.
RF tests use the declared `rf` extra (`numpy`, `scikit-rf`) and independent
attenuator, resistor, line and matching equations. Preserve port/reference
conventions and distinguish full-matrix passivity from individual port-power
checks. Archive-only tests use a fresh interpreter so editable source installs
cannot silently stand in for Store packages.
RF robustness tests must compare exported complex S data with independent
circuit equations at every declared corner and grid, retain failed original
limits, and distinguish valid negative diagnosis from passing design. Cover
common choices, exact decimal tolerance products, worst-frequency/headroom
witnesses, numerical refinement failure and complete Cartesian coverage.
Test unequal port references when frequency count equals port count: library
vector-shape inference must not reinterpret them as frequency-dependent values.
Test inclusive decimal headroom and one-floating-step failures on both sides
without epsilon widening. Selected-band dB checks must ignore unrelated nulls
but reject zeros in the window or interpolation brackets; phase keeps its
original global unwrap branch.
PCB tests require KiCad 9 `kicad-cli` and the declared `pcb` extra (`sexpdata`).
The original local-library coupon exercises real ERC, DRC with parity and
Gerber/Excellon generation. Deliberate defects must fail native checks; changing
both saved output copies must still fail independent temporary replay. Keep
unsupported zone forms and advanced drills explicit rather than trusting stale fill.
PCB copper-zone tests additionally execute the official KiCad 9 `pcbnew`
binding in a separate system Python process (the KiCad package installed in CI
includes it). Require exact CLI/binding version agreement. Preserve original
and frozen inputs, discard old fills, and use one refilled working board for
checks and exports. Cover custom-rule parse failures and actual clearance
effects; KiCad's `LoadBoard` alone can hide invalid custom rules.
Package thermal tests require native `gmsh` and `ccx` (`calculix-ccx` on Ubuntu)
plus the `package` numpy extra. Preserve actual mesh/solver output, conserved
surface loads and native heat balance. Check independent series-resistance
equations and actual refinement for lateral spreading; two meshes are not a
proof of absolute discretization error. Failed original bounds stay failed.
Convection tests additionally cover native FILM face numbering, exterior
ledges without internal-interface cooling, common-ambient temperature-rise
representation, tiny signals, analytic conduction-plus-film resistance,
overlapping heated/cooled nodes and C3D4 centroid film quadrature. Require
unchanged ambient, coefficient and selected faces under refinement; a finished
job message never overrides a nonzero actual solver exit.
Power-converter tests use native ngspice >=42 and the `power` numpy extra.
Preserve adaptive sample times, source-current signs and stored L/C energy;
transient input/output mismatch is not automatically dissipation. Check actual
startup/load changes, steady-cycle behavior, original CCM references and
time-step comparisons. Native execution has explicit time/output-size bounds.
`argus_verticals/hardware/spice/` is the shared native reader, not a provider;
analog's previous `raw` imports remain compatible without workflow inheritance.
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
