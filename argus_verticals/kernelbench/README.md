# kernelbench

**Purpose:** maximize correctness-checked SOL score/speedup for GPU kernels on B200 SOL-ExecBench/KernelBench.

Optimize-kind mission on top of Argus's speedrun base contract (`argus_skill.verticals.optimization_base`) with a `metric` completion gate; inherits `kernel_engineering`'s skills (`VERTICAL_SKILL_PARENTS = ("kernel_engineering",)`).

- `stages.py`: `research → setup → optimize → measure → report`, KernelBench evidence checks (`argus_skill.verticals.metric_evidence`).
- `official_eval_server.py`: thin HTTP wrapper around the official evaluator; signs only full-coverage results (`argus_skill.team.result_provenance`).
- `skills/engineer/` plus three top-level skill cards on target selection, report-only evidence, and verifier drift.

Extras: none (the evaluator itself is external). Tests: `tests/test_eval_signing.py`.
