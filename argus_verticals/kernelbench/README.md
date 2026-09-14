# kernelbench

**Purpose:** maximize correctness-checked SOL score/speedup for GPU kernels on B200 SOL-ExecBench/KernelBench.

Optimize-kind mission on top of Argus's speedrun base contract (`argus.verticals.optimization_base`) with a `metric` completion gate; inherits `kernel_engineering`'s skills (`VERTICAL_SKILL_PARENTS = ("kernel_engineering",)`).

- `stages.py`: `research → setup → optimize → measure → report`, KernelBench evidence checks (`argus.verticals.metric_evidence`).
- `official_eval_server.py`: thin HTTP wrapper around the official evaluator; signs only full-coverage results (`argus.team.result_provenance`).
- `skills/engineer/`: B200 runtime, official SOL-ExecBench environment, hands-on trace and SOTA optimisation playbooks, plus three Engineer playbooks on target selection without execution, report-only head-to-head evidence, and governance-verifier drift repair.

Extras: none (the evaluator itself is external). Tests: `tests/test_eval_signing.py`.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
