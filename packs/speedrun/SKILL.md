---
name: speedrun
description: "single-metric script/benchmark optimization under a wall-clock budget: setup, optimize, measure, report; no paper"
version: 0.2.0
---

# speedrun

single-metric script/benchmark optimization under a wall-clock budget: setup, optimize, measure, report; no paper.

## What counts as done

### setup

- **setup.solution_self_contained** — What the mission asks for is the EDITABLE file it names (a recipe / solution file / kernel) that uses the mission's FROZEN harness/scorer UNCHANGED and modifies ONLY that editable file. The reviewer must confirm the agent did NOT touch the harness, the evaluation, the metric, the held-out data, or the budget — they are byte-identical to the scaffold (`git diff` or a byte comparison against the pinned scaffold) — and that the candidate is scored through the mission's frozen scorer exactly as the mission specifies.
  Evidence hint: the editable file + an empty harness `git diff` vs the pinned scaffold + a run log produced through the mission's frozen scorer

- **setup.heldout_val** — Evaluation reads the HELD-OUT / contract-specified inputs wired by the frozen harness, and there is NO leakage or exploit: the candidate does not see, memorise, or HARDCODE the known eval inputs/answers, and the metric / eval inputs are the scaffold's, untouched. The reward must reflect genuine generalisation, so a candidate that obtains its score by encoding the known eval distribution (e.g. baking in fixed statistics of the test inputs) rather than COMPUTING the real result is disqualified — that is a reward hack, not a result.
  Evidence hint: the harness's eval wiring + the candidate showing it COMPUTES the real result rather than encoding/hardcoding the known eval inputs

### optimize

- **optimize.metric_curve** — The mission metric over the run MOVES THE RIGHT WAY (the candidate is actually improving within the budget), OR any flat / wrong-way / noisy / early-plateau trajectory is EXPLICITLY explained (e.g. budget-bound, schedule, warmup, divergence) rather than silently accepted. A trajectory that never improves over the starting point is a dead attempt, not a result. No real trajectory means this item is UNSATISFIED: an external launch rejection may justify a blocked mission, but never optimize-stage completion.
  Evidence hint: the metric-vs-step (or vs-wall-clock) series in the run log; a one-line explanation for any non-improving trajectory

### measure

- **measure.repeat_mean_metric** — The reported result is the AGGREGATE mission metric across N repeats (iterate at small N, report the final number at higher N) — NOT a single lucky run and NEVER the number the candidate printed about itself. A per-repeat record captures each run's metric as RE-MEASURED by the VERIFIER re-running the candidate through the frozen scorer under the identical protocol; the headline the reviewer trusts is the verifier's, because the agent edits only the editable file and can self-report anything.
  Evidence hint: per-repeat record (run, metric) from the verifier's re-runs + the computed aggregate; each row traceable to a real frozen-scorer output line

- **measure.budget_respected** — Every scored run respected the FIXED budget the mission declares (wall-clock and hardware) — the candidate did not extend, bypass, or hand-tune the budget, and no scored run exceeded it. The contest is the BEST metric reachable UNDER the fixed budget, so a candidate that only attains its score by exceeding the budget is invalid; the budget in the frozen harness stays unchanged.
  Evidence hint: per-run wall-clock within the declared budget in the run log / manifest; the budget in the frozen harness unchanged

### report

- **report.beats_baseline** — The proposed candidate's metric BEATS the RE-MEASURED baseline: the named reference baseline re-run ON OUR harness and hardware under the identical protocol (same repeats, same budget, same held-out eval) — NOT a published number from different hardware. The comparison is head-to-head and cites BOTH per-run records (ours and the re-measured baseline's) so the win is a like-for-like delta, not a measurement artifact of differing hardware or protocol. If the candidate does NOT beat the re-measured baseline, say so plainly and queue a repair/pivot — do not relabel a loss as a win.
  Evidence hint: two per-run records (proposed vs re-measured baseline) under the identical protocol + the metric delta; baseline re-run on our hardware, not a published number from other hardware

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/evidence.py' --help
python3 '<this folder>/evidence.py' speedrun --project-root .
```

The check finds `attempts/**/results.csv` or `experiments/**/results.csv` with at least one finite value in `val_bpb`, `mean_val_bpb`, `seconds_to_target`, `wall_seconds`, `score`, or `metric_value`. Exit 0 prints the accepted file; exit 1 means evidence is absent or invalid. It checks structure, not scientific validity, repeat count, provenance, budget compliance, or a baseline win. For another mission metric, record its value in `metric_value` as well as the task's original field. A final report also needs a non-empty project `RESULTS.md` and the repeat/baseline evidence described above; inspect these separately.

Run optimization and measurement with the frozen scorer supplied by the task. The commands and files in the two role references are a historical NanoGPT example, not bundled executables: `eval_solution.sh`, `analyze_sweep.py`, `solution/`, `research/`, and `experiments/` belong to that benchmark/project. Replace example paths, versions and hardware only as the task's protocol permits. The two companion references link to each other inside this pack; single-kernel procedures mentioned as a different use case must come from the task.

## Needs

Python 3.10+; bundled evidence check uses only the standard library and needs no GPU. Optimization runs need the task's frozen scorer, inputs, benchmark software and declared hardware; the NanoGPT trace specifically needs its original 8xH100 harness and software. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [speedrun-hands-on-trace.md](skills/engineer/speedrun-hands-on-trace.md)

- engineer: [speedrun-sota-optimization.md](skills/engineer/speedrun-sota-optimization.md)


## Supporting files

- [LICENSE](LICENSE)

- [evidence.py](evidence.py)
