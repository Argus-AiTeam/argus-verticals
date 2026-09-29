# argus-verticals

Community-maintained **verticals** (domain packs) for
[Argus](https://github.com/lbx154/Argus), the persistent, reviewed runtime for
autonomous research and engineering.

A vertical tells Argus how one kind of work is done: the ordered stages, the
per-stage review checklists, what counts as done (`completion_gate`), which
role banners the Manager, Planner, Engineer and Reviewer read, and the Skill
markdown those roles are seeded with. Argus ships seven built-in
verticals (`research`, `software`, `kernel_engineering`, `learning`,
`argus_maintenance`, `math`, `math_synth`). Everything domain-specific beyond
that lives here.

## How Argus finds these verticals

Argus discovers out-of-tree verticals through the Python entry-point group
`argus.verticals` (`argus/verticals/_registry.py`). Every entry in
this package's `pyproject.toml` points at a `stages.py` module that declares:

| attribute | meaning |
|---|---|
| `ARGUS_VERTICAL_API_VERSION = 1` | must equal Argus's `VERTICAL_API_VERSION`; a mismatch means the plugin is ignored with a log line |
| `VERTICAL_PURPOSE` | the one-line menu entry the Manager reads when it decides which vertical a task belongs to |
| `VERTICAL_SKILLS` (optional) | path to the vertical's `skills/` tree; Argus seeds it exactly like a built-in's |
| `VERTICAL_SKILL_PARENTS` | verticals whose skill trees are seeded before this one's (for example `kernelbench` inherits `kernel_engineering`) |
| `VERTICAL_ROUTING_PATH` (optional) | category, domain and optional specialty; navigation/routing only, not workflow or knowledge inheritance |

Once the package is installed, a discovered vertical is treated like a
built-in: same Manager menu, same Skill seeding, same stage machine, same
Reviewer. Argus validates every plugin with the same
`argus.core.vertical_contract.vertical_contract` check it applies to its
own verticals, and drops (with a warning) any that fail.

## Install

Install Argus first, then this package into the same Python environment.
Argus is installed from its repository, not from PyPI, so this package
declares no pip dependency on it (a requirement could neither be resolved
nor express "at or after the split"):

```bash
pip install "argus @ git+https://github.com/lbx154/Argus.git@main"
pip install "argus-verticals @ git+https://github.com/Argus-AiTeam/argus-verticals.git"
# pip install argus-verticals            # PyPI release planned
```

The Argus you install must be **at or after the 2026-09-14 split**: the commit
that made vertical discovery dynamic and added `VERTICAL_SKILL_PARENTS`. An
older Argus still lists these 17 verticals as built-ins and ignores skill
parents; against such an install the conformance test fails with
"Argus is older than the verticals split; update Argus".

It must also include the **2026-09-14 package rename**: on the same day the
Python package `argus_skill` became `argus` and the pip distribution
`argus-skill` became `argus`. This package imports `argus` and registers its
entry points under the `argus.verticals` group, so an Argus from before the
rename cannot import it; the conformance test then fails with "Argus is older
than the argus_skill → argus rename; update Argus". If a distribution still
named `argus-skill` is installed, `pip uninstall argus-skill` before installing
`argus`. Persisted names did not move with the rename: the `ARGUS_SKILL_*`
environment variables, the state root `~/.argus-skill` and the other on-disk
markers keep their spelling.

That is all: the next `argus` start sees the new verticals in the
Manager's menu. Optional extras:

```bash
pip install "argus-verticals[quant]"    # numpy/pandas/scipy/scikit-learn/matplotlib/mplfinance/lightgbm/torch for the quant toolkits
pip install "argus-verticals[literary]" # jsonschema + PyYAML, the literary verticals' shared contracts (also pulled in by [dev])
pip install "argus-verticals[zh-fold]"  # opencc, traditional/simplified folding for the literary novelty check
```

The packaged desktop build of Argus bundles only Argus's built-in verticals;
install this package into the Python environment Argus runs from to add these.

## Verticals

Hardware routing separates category, primary domain and independent specialty.
The digital verification specialty and FPGA domain are joined by
`analog_mixed_signal`, whose initial executable support is scoped ngspice
operating-point, DC, AC and transient analysis, not a PDK or physical-design flow.
`rf_design` adds independent scikit-rf network studies: Touchstone data,
matching models, explicit port/reference handling and two-port cascades.
`pcb_design` adds independent PCB knowledge and selected native KiCad 9 ERC,
DRC/parity and Gerber/Excellon generation with temporary native replay.
The agreed broader taxonomy also reserves separate **conceptual areas** for
packaging and power electronics. They are not
registered or advertised as supported verticals yet: each needs its own tools,
evidence interpretation and executable references before publication.
The existing `chip_design` architecture model remains accelerator-oriented in
this batch; a general control-SoC model and independent physical/DFT execution
are still separate work, not capabilities implied by the taxonomy.

| entry point | module | purpose (as shown in the Manager's menu) | skill parents |
|---|---|---|---|
| `ale_last_exam` | `argus_verticals.ale_last_exam` | Agents' Last Exam long-horizon professional workflow in a real sandbox with hidden-reference, artifact-first GUI+CLI delivery | |
| `analog_mixed_signal` | `argus_verticals.analog_mixed_signal` | analog/mixed-signal knowledge and scoped native ngspice analysis with explicit model limits | |
| `chip_design` | `argus_verticals.chip_design` | end-to-end digital ASIC/accelerator design from workload and microarchitecture through RTL, physical implementation, and sign-off | `digital_circuit` |
| `classical_poetry` | `argus_verticals.classical_poetry` | compose or check classical Chinese 近体诗/古体/词 with reproducible 押韵/平仄 prosody and literary review | |
| `digital_circuit` | `argus_verticals.digital_circuit` | Verilog/SystemVerilog RTL, testbenches, formal verification, FPGA/ASIC synthesis, timing, and sign-off | |
| `digital_circuit_benchmark` | `argus_verticals.digital_circuit.benchmark` | single-stage fixed-harness RTL benchmark: interface, RTL, local verification, pre-score elaboration, and attempt handoff | `digital_circuit` |
| `digital_circuit_verification` | `argus_verticals.digital_circuit.verification` | independent configuration/scenario regression and nonvacuous formal checks | `digital_circuit` |
| `fpga_design` | `argus_verticals.fpga_design` | scoped FPGA work with single-clock iCE40 implementation and measured board acceptance | `digital_circuit`, `digital_circuit_verification` |
| `fiction_writing` | `argus_verticals.fiction_writing` | write or continue original fiction narrative prose while preserving characters, world, and timeline; not a literature review or research task | |
| `kernelbench` | `argus_verticals.kernelbench` | maximize correctness-checked SOL score/speedup for GPU kernels on B200 SOL-ExecBench/KernelBench | `kernel_engineering` (Argus built-in) |
| `literary_editor` | `argus_verticals.literary_editor` | rewrite, expand, polish, proofread, or critique an existing literary text while preserving edit scope and source facts | |
| `materials` | `argus_verticals.materials` | materials science and materials processing across atomistic, microstructure, continuum, CAD/CAE, and experimental scales | |
| `medical` | `argus_verticals.medical` | biomedical and pharmaceutical evidence execution: target-disease mechanisms, human genetics, preclinical translation, clinical trials, safety, failed programs, competitive pipelines, and auditable non-diagnostic decision dossiers with independent review; not a generic paper pipeline | |
| `modern_poetry` | `argus_verticals.modern_poetry` | compose or revise modern free verse/prose poems without classical prosody checks; enforce only declared hard constraints | |
| `nanochat` | `argus_verticals.nanochat` | minimize val_bpb on the nanochat train.py (bits-per-byte, ~300s, 1 GPU) | |
| `nanogpt_speedrun` | `argus_verticals.nanogpt_speedrun` | minimize wall-clock time to reach val_loss<=3.28 on modded-nanogpt (8xH100) | `speedrun` |
| `physics` | `argus_verticals.physics` | theory, simulation, data analysis, literature, or experiment design for a real physical system with bounded evidence | |
| `pcb_design` | `argus_verticals.pcb_design` | PCB engineering and selected native KiCad checks, parity and manufacturing-file generation; no physical qualification | |
| `prose` | `argus_verticals.prose` | compose or revise literary essays, memoir, or 抒情/叙事散文/随笔; not verse or plot-driven fiction | |
| `quant` | `argus_verticals.quant` | equity factor research (IC/ICIR, backtest, Sharpe) producing a reviewer-certified report, not a generic metric loop | |
| `rf_design` | `argus_verticals.rf_design` | RF knowledge and scoped Touchstone, matching, reference-change and cascade studies using scikit-rf | |
| `speedrun` | `argus_verticals.speedrun` | single-metric script/benchmark optimization under a wall-clock budget: setup, optimize, measure, report; no paper | |

`argus_verticals/literary/shared/` is not a vertical. It is the helper package
the five literary verticals (fiction_writing, classical_poetry, modern_poetry,
prose, literary_editor) share: the task envelope, the structured review
contract, the artifact manifest, the source registry and its provenance log,
each with a JSON schema.

`argus_verticals/hardware/shared/` similarly shares file/copy/numeric record
utilities between independent hardware domains, without inheriting their
knowledge, stages or acceptance methods.

Each vertical directory has its own `README.md` with its modules, the extras
it needs, and the tests that cover it.

## Store metadata

Besides the pip route above, Argus's **Vertical Store** (UI and CLI) installs
verticals from this repository one directory at a time, without pip. Three
files make that possible; all of them are generated or validated by
`scripts/build_catalog.py`, which is standard-library only and imports nothing
from Argus.

**`argus_verticals/<name>/vertical.json`** — the per-vertical manifest, next to
`stages.py`, validated against [`catalog/vertical.schema.json`](catalog/vertical.schema.json):

| field | meaning |
|---|---|
| `name`, `module` | the entry-point name and target from `pyproject.toml`; the generator fails if they disagree |
| `version` | semver of this directory; bump it when anything under `paths` changes (see CONTRIBUTING) |
| `purpose_zh` | optional Chinese one-liner for the store; the English `VERTICAL_PURPOSE` is *not* repeated here, the generator reads it from `stages.py` |
| `paths` | repo-relative directories that make up the vertical (`["argus_verticals/quant"]`; a vertical nested in another's directory, like `digital_circuit/benchmark`, is never part of the parent's archive) |
| `requires` | other catalog verticals the store installs alongside: the code imports them (`chip_design` → `digital_circuit`) or `VERTICAL_SKILL_PARENTS` names them (`nanogpt_speedrun` → `speedrun`); Argus built-ins such as `kernel_engineering` are not listed |
| `shared` | helper directories bundled into the archive because the code imports them (the five literary verticals → `argus_verticals/literary/shared`) |
| `python_requirements`, `optional_python_requirements` | pip requirements the runtime code imports, unguarded or behind a guard, spelled exactly as in an extra of `pyproject.toml`; the store shows them, it does not install them |
| `tags`, `maintainers`, `min_argus` | 2–4 browsing tags; GitHub handles; the Argus commit family the vertical is written for (`2026-09-14-split`; the store compares by feature probe, not by this string) |

**`catalog.json`** at the repository root — the browsing index, committed and
kept current by CI (`python scripts/build_catalog.py --check` fails when it is
stale). For every vertical it holds the manifest fields plus what the
generator derives by parsing `stages.py` with `ast`: `purpose`,
`skill_parents`, `has_skills`, `api_version`, and `size_bytes`. Keys are
sorted and there are no timestamps, so the file only changes when a vertical
does; `generated_from.commit` records the commit it was built at and is
ignored by `--check`.

**GitHub Releases** — pushing a repository-wide tag `vX.Y.Z` runs
[`release.yml`](.github/workflows/release.yml), which builds
`python scripts/build_catalog.py --release vX.Y.Z --dist dist` and attaches to
the release one `<name>-<version>.zip` per vertical (exactly the `paths` +
`shared` trees with their repo-relative paths, no `__pycache__`, no tests,
fixed timestamps so a rebuild is byte-identical), `dist/catalog.json` (the
index plus, per vertical, `archive: {file, url, sha256, size}`), and
`dist/SHA256SUMS`. The store reads `dist/catalog.json`, downloads the zip,
verifies the sha256, extracts it under
`<ARGUS_SKILL_HOME>/verticals/argus_verticals/<name>/` (no `__init__.py` is
written: Argus registers `argus_verticals` as a namespace package, or appends
the store directory to an installed pip copy's `__path__`), and loads
`argus_verticals.<name>.stages` from there; `tests/test_catalog.py` rehearses exactly that round trip for every
archive.

```bash
python scripts/build_catalog.py                       # rewrite catalog.json
python scripts/build_catalog.py --check               # CI: is the committed index current?
python scripts/build_catalog.py --release v0.2.0 --dist dist   # archives + dist/catalog.json + SHA256SUMS
python scripts/build_catalog.py --verify dist         # digests, member lists, byte-identical rebuild
```

## Add your own vertical

1. **Copy the smallest vertical with a full four-role skills tree as a
   template.** `argus_verticals/materials/` is a good start: one `stages.py`, one `evidence.py`, a full
   `skills/{manager,planner,engineer,reviewer}/` tree, a `README.md`, and one
   test file. Rename the directory to your vertical's name (`^[a-z][a-z0-9_]{0,47}$`).
2. **Lay it out like this:**
   ```
   argus_verticals/<name>/
     __init__.py
     stages.py            # the contract (see the table below)
     <helpers>.py         # deterministic checks, evidence readers, CLIs
     skills/
       manager/*.md  planner/*.md  engineer/*.md  reviewer/*.md
     README.md
   tests/test_<name>_*.py
   ```
   A skill file is Argus's format: a `---` front matter with `name` and
   `description`, then free Markdown. Put every file under a role directory;
   a role-less file at the top of `skills/` is seeded without a role and is
   permitted but discouraged. Scripts a skill invokes live in a `*_scripts/`
   directory next to it (`engineer/<skill>_scripts/tool.py`) and are seeded
   verbatim.
3. **Declare the plugin attributes** near the top of `stages.py`:
   ```python
   ARGUS_VERTICAL_API_VERSION = 1
   VERTICAL_PURPOSE = "one line the Manager can route on; say what it is NOT when a neighbour exists"
   VERTICAL_SKILLS = Path(__file__).resolve().parent / "skills"   # omit if you ship no skills/
   VERTICAL_SKILL_PARENTS: tuple[str, ...] = ()                    # e.g. ("digital_circuit",)
   ```
4. **Implement the contract** in the same module: `CHECKLIST_STAGE_ORDER`,
   `CHECKLIST_ITEMS`, `completion_gate`, and whichever optional fields your
   workflow needs (table below). Import framework helpers from `argus`
   (for example `from argus.skills.stage_machine import ChecklistItem`);
   import other verticals only through `argus_verticals.<name>` or a shared
   helper package.
5. **Register the entry point** in `pyproject.toml`, name = directory name
   (nested directories join with `_`):
   ```toml
   [project.entry-points."argus.verticals"]
   my_vertical = "argus_verticals.my_vertical.stages"
   ```
6. **Write `vertical.json`** next to `stages.py` (copy a neighbour's; fields in
   [Store metadata](#store-metadata)) and run `python scripts/build_catalog.py`
   to regenerate `catalog.json`. Start at `"version": "0.1.0"`; list in
   `requires` every catalog vertical you import or inherit skills from, and in
   `shared` every helper directory you import.
7. **Write tests** under `tests/` for your deterministic checks, and a
   `README.md` in the vertical directory (purpose, modules, extras, tests, and
   the line ``Manifest: `vertical.json` ``).
8. **Run the gate:**
   ```bash
   pip install -e ".[dev]"
   ruff check argus_verticals tests scripts
   python scripts/build_catalog.py --check
   pytest -q tests/test_contract_conformance.py tests/test_catalog.py   # then the full suite: pytest -q
   ```
   The conformance test imports every entry point, checks the four plugin
   attributes, runs Argus's own `vertical_contract` validation, and fails if a
   directory with a `stages.py` is not registered (or vice versa). The catalog
   test checks the manifest against the schema, `pyproject.toml`, and your
   actual imports.
9. **Open a pull request.** See [CONTRIBUTING.md](CONTRIBUTING.md) for the
   rules a reviewer applies.

## The contract, in short

Argus reads these attributes off the `stages` module and freezes them into a
`VerticalContract` (`argus/core/vertical_contract.py` in Argus is the
authoritative definition; this table is a summary).

| attribute on `stages.py` | type / closed vocabulary | notes |
|---|---|---|
| `CHECKLIST_STAGE_ORDER` | `tuple[str, ...]`, required, unique names | the ordered stages of a mission |
| `CHECKLIST_ITEMS` | `dict[stage, tuple[ChecklistItem, ...]]`, required | every stage needs a non-empty list unless listed in `CHECKLIST_OPTIONAL_STAGES`; item ids unique per stage |
| `CHECKLIST_OPTIONAL_STAGES` | `tuple[str, ...]` ⊆ stage order | stages that may run without a checklist |
| `completion_gate` | `"none"` \| `"metric"` \| `"certified"` | how the final stage closes: reviewer judgment, a measured metric, or a certified deliverable |
| `WORKFLOW_MODE` | `"staged"` \| `"direct"` \| `"proportional"` (default `staged`) | strict stage order, single-stage direct execution, or reusable upstream evidence |
| `MISSION_KIND` | `"custom"` \| `"optimize"` \| `"research"` \| `"software"` (default `custom`) | steers the Manager's mission framing |
| `VERIFICATION_STAGE_PROFILES` | `dict[stage, "explore" \| "develop" \| "certify"]` | how hard the Engineer verifies in each stage |
| `REQUIRE_INDEPENDENT_REVIEW` | `bool` (default `True`) | every mission ends with a Reviewer |
| `PAPER_MISSION` | `bool` | the deliverable is a paper |
| `RESEARCH_TARGET_LEVELS` | `tuple[str, ...]` | e.g. `("exploratory", "publishable", "doctoral")` |
| `STAGE_ALIASES` | `dict[alias, canonical stage]` | accepted non-canonical stage names |
| `STAGE_PRIMARY_DELIVERABLES` | `dict[stage, tuple[path, ...]]` | what a stage must produce |
| `ENGINEER_STAGE_OPERATIONS`, `ENGINEER_LIVE_SEARCH_STAGES` | `dict[stage, str]`, collection of stages | per-stage Engineer operating notes; stages that may search the live web |
| `ALLOW_STAGE_ROLLBACK`, `COMPLETION_CONTRACT_VERSION`, `GROUND_BEFORE_HANDOFF` | `bool`, `int`, `bool` | rollback permission, versioned final-stage contract, grounding before role handoff |
| `role_banner(role) -> str` | callable | the banner each role reads (`manager`, `planner`, `engineer`, `reviewer`) |
| `stage_completion_issues(stage, project_root, *, state_root=None) -> tuple[str, ...]` | callable | deterministic pre-completion validator; empty tuple means no machine objection |
| `planner_task_issues`, `automatic_stage_completion_ready`, `prepare_mission`, `iteration_assessment`, `review_purchase_policy`, `adopt_operator_objective`, `import_legacy_state`, `search_altitude_context`, `render_role_prompt_fragment`, `render_role_prompt_context`, `LIBRARY_PREPARER`, `EVIDENCE_SCHEMA` | optional hooks | see the docstrings in Argus's `vertical_contract.py`; each is called with keyword arguments and a stale signature halts the run visibly |

## Development

```bash
git clone https://github.com/Argus-AiTeam/argus-verticals.git
cd argus-verticals
pip install "argus @ git+https://github.com/lbx154/Argus.git@main"   # at or after the 2026-09-14 split and argus_skill → argus rename
pip install -e ".[dev,zh-fold]"
ruff check argus_verticals tests scripts
python scripts/build_catalog.py --check
pytest -q
```

Tests that need `lightgbm`, `torch`, `qlib`, or `adata` skip when those are
not installed. When the package is not installed (`pip install -e .` not run),
`tests/conftest.py` registers the checkout's own entry points for the session
so the suite still exercises Argus's registry and seeder; when it is installed,
the conformance test fails on metadata that no longer matches `pyproject.toml`
("stale install — re-run pip install -e .").

## License

MIT, see [LICENSE](LICENSE).
