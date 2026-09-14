# speedrun

**Purpose:** single-metric script/benchmark optimization under a wall-clock budget: setup, optimize, measure, report; no paper.

Optimize-kind mission `setup → optimize → measure → report` with a `metric` completion gate, built on Argus's `argus_skill.verticals.optimization_base`. `nanogpt_speedrun` inherits this skill tree; `nanochat` and `kernelbench` reuse the same base contract.

- `stages.py`: contract, role banners, speedrun evidence checks (`argus_skill.verticals.metric_evidence`). The per-stage reviewer checklist is Argus's `OPTIMIZATION_CHECKLIST_ITEMS` (`argus_skill.verticals.optimization_base`), reused rather than copied, so the built-in `math_synth` and the optimization verticals here share one table.
- `skills/engineer/speedrun-hands-on-trace.md`, `skills/engineer/speedrun-sota-optimization.md`.

Extras: none. Tests: covered by `tests/test_contract_conformance.py`, `tests/test_voice_wordlist.py`, and indirectly by `tests/skills/test_nanogpt_speedrun_vertical.py`.
