# argus-verticals

Community-maintained **verticals** (domain packs) for
[Argus](https://github.com/lbx154/Argus), the persistent, reviewed runtime for
autonomous research and engineering.

A vertical tells Argus how one kind of work is done: the ordered stages, the
per-stage review checklists, what counts as done (`completion_gate`), which
role banners the Manager, Planner, Engineer and Reviewer read, and the Skill
markdown those roles are seeded with. Argus ships a small set of built-in
verticals (research, software, math, kernel_engineering, learning, and its own
maintenance). Everything domain-specific beyond that lives here.

## How Argus finds these verticals

Argus discovers out-of-tree verticals through the Python entry-point group
`argus_skill.verticals` (`argus_skill/verticals/_registry.py`). Every entry in
this package's `pyproject.toml` points at a `stages.py` module that declares:

| attribute | meaning |
|---|---|
| `ARGUS_VERTICAL_API_VERSION = 1` | must equal Argus's `VERTICAL_API_VERSION`; a mismatch means the plugin is ignored with a log line |
| `VERTICAL_PURPOSE` | the one-line menu entry the Manager reads when it decides which vertical a task belongs to |
| `VERTICAL_SKILLS` (optional) | path to the vertical's `skills/` tree; Argus seeds it exactly like a built-in's |
| `VERTICAL_SKILL_PARENTS` | verticals whose skill trees are seeded before this one's (for example `kernelbench` inherits `kernel_engineering`) |

Once the package is installed, a discovered vertical is treated like a
built-in: same Manager menu, same Skill seeding, same stage machine, same
Reviewer. Argus validates every plugin with the same
`argus_skill.core.vertical_contract.vertical_contract` check it applies to its
own verticals, and drops (with a warning) any that fail.

## Install

```bash
pip install argus-verticals                     # PyPI release planned
# or, straight from the repository
pip install "argus-verticals @ git+https://github.com/Argus-AiTeam/argus-verticals.git"
```

That is all: the next `argus-skill` start sees the new verticals in the
Manager's menu. Optional extras:

```bash
pip install "argus-verticals[quant]"    # numpy/pandas/scipy/scikit-learn/matplotlib/mplfinance/lightgbm/torch for the quant toolkits
pip install "argus-verticals[zh-fold]"  # opencc, traditional/simplified folding for the literary novelty check
```

The packaged desktop build of Argus bundles only Argus's built-in verticals;
install this package into the Python environment Argus runs from to add these.

## Verticals

| entry point | module | purpose (as shown in the Manager's menu) | skill parents |
|---|---|---|---|
| `ale_last_exam` | `argus_verticals.ale_last_exam` | Agents' Last Exam long-horizon professional workflow in a real sandbox with hidden-reference, artifact-first GUI+CLI delivery | |
| `chip_design` | `argus_verticals.chip_design` | end-to-end digital ASIC/accelerator design from workload and microarchitecture through RTL, physical implementation, and sign-off | `digital_circuit` |
| `classical_poetry` | `argus_verticals.classical_poetry` | compose or check classical Chinese 近体诗/古体/词 with reproducible 押韵/平仄 prosody and literary review | |
| `digital_circuit` | `argus_verticals.digital_circuit` | Verilog/SystemVerilog RTL, testbenches, formal verification, FPGA/ASIC synthesis, timing, and sign-off | |
| `digital_circuit_benchmark` | `argus_verticals.digital_circuit.benchmark` | single-stage fixed-harness RTL benchmark: interface, RTL, local verification, pre-score elaboration, and attempt handoff | `digital_circuit` |
| `fiction_writing` | `argus_verticals.fiction_writing` | write or continue original fiction narrative prose while preserving characters, world, and timeline; not a literature review or research task | |
| `kernelbench` | `argus_verticals.kernelbench` | maximize correctness-checked SOL score/speedup for GPU kernels on B200 SOL-ExecBench/KernelBench | `kernel_engineering` (Argus built-in) |
| `literary_editor` | `argus_verticals.literary_editor` | rewrite, expand, polish, proofread, or critique an existing literary text while preserving edit scope and source facts | |
| `materials` | `argus_verticals.materials` | materials science and materials processing across atomistic, microstructure, continuum, CAD/CAE, and experimental scales | |
| `medical` | `argus_verticals.medical` | biomedical and pharmaceutical evidence execution: target-disease mechanisms, human genetics, preclinical translation, clinical trials, safety, failed programs, competitive pipelines, and auditable non-diagnostic decision dossiers with independent review; not a generic paper pipeline | |
| `modern_poetry` | `argus_verticals.modern_poetry` | compose or revise modern free verse/prose poems without classical prosody checks; enforce only declared hard constraints | |
| `nanochat` | `argus_verticals.nanochat` | minimize val_bpb on the nanochat train.py (bits-per-byte, ~300s, 1 GPU) | |
| `nanogpt_speedrun` | `argus_verticals.nanogpt_speedrun` | minimize wall-clock time to reach val_loss<=3.28 on modded-nanogpt (8xH100) | `speedrun` |
| `physics` | `argus_verticals.physics` | theory, simulation, data analysis, literature, or experiment design for a real physical system with bounded evidence | |
| `prose` | `argus_verticals.prose` | compose or revise literary essays, memoir, or 抒情/叙事散文/随笔; not verse or plot-driven fiction | |
| `quant` | `argus_verticals.quant` | equity factor research (IC/ICIR, backtest, Sharpe) producing a reviewer-certified report, not a generic metric loop | |
| `speedrun` | `argus_verticals.speedrun` | single-metric script/benchmark optimization under a wall-clock budget: setup, optimize, measure, report; no paper | |

`argus_verticals/literary/shared/` is not a vertical. It is the helper package
the five literary verticals (fiction_writing, classical_poetry, modern_poetry,
prose, literary_editor) share: the task envelope, the structured review
contract, the artifact manifest, the source registry and its provenance log,
each with a JSON schema.

Each vertical directory has its own `README.md` with its modules, the extras
it needs, and the tests that cover it.

## Add your own vertical

1. **Copy the smallest vertical as a template.** `argus_verticals/materials/`
   is a good start: one `stages.py`, one `evidence.py`, a full
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
   Skill markdown uses Argus's format: a `---` front matter with `name` and
   `description`, then `## When to use` and `## How to solve`.
3. **Declare the plugin attributes** near the top of `stages.py`:
   ```python
   ARGUS_VERTICAL_API_VERSION = 1
   VERTICAL_PURPOSE = "one line the Manager can route on; say what it is NOT when a neighbour exists"
   VERTICAL_SKILLS = Path(__file__).resolve().parent / "skills"   # omit if you ship no skills/
   VERTICAL_SKILL_PARENTS: tuple[str, ...] = ()                    # e.g. ("digital_circuit",)
   ```
4. **Implement the contract** in the same module: `CHECKLIST_STAGE_ORDER`,
   `CHECKLIST_ITEMS`, `completion_gate`, and whichever optional fields your
   workflow needs (table below). Import framework helpers from `argus_skill`
   (for example `from argus_skill.skills.stage_machine import ChecklistItem`);
   import other verticals only through `argus_verticals.<name>` or a shared
   helper package.
5. **Register the entry point** in `pyproject.toml`, name = directory name
   (nested directories join with `_`):
   ```toml
   [project.entry-points."argus_skill.verticals"]
   my_vertical = "argus_verticals.my_vertical.stages"
   ```
6. **Write tests** under `tests/` for your deterministic checks, and a
   `README.md` in the vertical directory (purpose, modules, extras, tests).
7. **Run the gate:**
   ```bash
   pip install -e ".[dev]"
   ruff check argus_verticals tests
   pytest -q tests/test_contract_conformance.py   # then the full suite: pytest -q
   ```
   The conformance test imports every entry point, checks the four plugin
   attributes, runs Argus's own `vertical_contract` validation, and fails if a
   directory with a `stages.py` is not registered (or vice versa).
8. **Open a pull request.** See [CONTRIBUTING.md](CONTRIBUTING.md) for the
   rules a reviewer applies.

## The contract, in short

Argus reads these attributes off the `stages` module and freezes them into a
`VerticalContract` (`argus_skill/core/vertical_contract.py` in Argus is the
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
pip install "argus-skill @ git+https://github.com/lbx154/Argus.git@main"
pip install -e ".[dev,zh-fold]"
ruff check argus_verticals tests
pytest -q
```

Tests that need `lightgbm`, `torch`, `qlib`, or `adata` skip when those are
not installed.

## License

MIT, see [LICENSE](LICENSE).
