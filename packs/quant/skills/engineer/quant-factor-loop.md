---
name: "Quant-Factor Loop Skill (Engineer)"
description: "Three-intent loop guide for the engineer doing quant factor research — select factors from the pool, evaluate a backtest result, and decide continue / stop / expand. Use during the run and analysis work so the loop stays disciplined and every trial goes through the BacktestExecutor."
---

## Title
Quant-Factor Loop Skill (Engineer)

## Description
Use this skill during the `run` and `analysis` work of a quant factor-research
task (see "What counts as done" in this pack's SKILL.md). It distils the
disciplined factor-mining loop the Reviewer expects to see in the search ledger
and the report.

## The three intents

You are running an iterative loop. On every round you must do exactly one of
the three intents below — never improvise a fourth.

### 1. `select_factors(pool, prior_history)`

Pick a subset of factor ids from the task's factor pool. Constraints:

- **Pick with intent.** Every factor in the subset must contribute a
  distinct dimension (size, value, momentum, quality, …). Do not duplicate a
  dimension — pick the better factor and drop the other.
- **First round** — pick from descriptions only. State the *expected sign*
  of each factor before you see any backtest number.
- **Later rounds** — pick informed by prior backtest rows: prefer survivors,
  drop the consistently weak. Quote the prior IC / Sharpe you are using as
  the basis for keeping or dropping.
- **Combination size** — start small (3–5 factors). Adding a sixth or
  seventh factor must be justified by an unfilled dimension, not by hope.

### 2. `evaluate_round(round_result)`

Critique the freshly returned backtest result. Constraints:

- Cite the **exact** Sharpe, IC, ICIR, turnover, and cost-adjusted return
  numbers — never paraphrase.
- Name the **strongest** factor in the combination and the **weakest** one,
  with the IC delta that justifies the call.
- Flag any **suspicious** outcome: IC > 0.10, Sharpe > 3, turnover > 200%
  per period, a flat long-short equity curve hiding inside a positive IC.
  These are usually data leakage, look-ahead, or a tiny denominator — not
  alpha.

### 3. `decide_next(history, latest_eval, pool)`

Choose exactly one of:

- `continue` — the loop has not converged and the pool has unexplored
  combinations worth trying. State the *next* combination you intend to
  test.
- `stop` — converged (last 2–3 rounds within tolerance, or returns are
  marginal versus search cost). State the converged Sharpe / IC range.
- `expand_pool` — the pool is missing a dimension and no combination of
  existing factors can fill it. State which dimension is missing and the
  rough shape of the factor that would fill it. Do not name a factor by
  ticker / column — describe the *concept*.

Be willing to **stop early**. More rounds is not always better.

## Backtest execution rule (non-negotiable)

Wrap the task's backtest engine (any object with `name` and
`run(spec) -> BacktestResult`) in this pack's executor and run every trial
through its `submit(spec)`:

```python
import sys; sys.path.insert(0, "<this folder>")  # the quant pack's folder
from backtest import BacktestSpec, ForcingExecutor
from search_ledger import SearchLedger
executor = ForcingExecutor(engine, SearchLedger("run/SEARCH_LEDGER.jsonl"))
result, row = executor.submit(BacktestSpec(run_id=..., factor_ids=[...], ...))
```

There is no other way to run a trial — calling the underlying engine
directly breaks the `run.search_ledger_complete` requirement, and the
Reviewer will send the run back.

For each trial, fill `BacktestSpec` with:

- `run_id`: a fresh uuid / timestamped string before execution
- `factor_ids`: the subset you chose
- `weighting`: `"equal_weight"` for combos, `"single"` for one-factor probes
- `window`: `"train"` / `"validation"` / `"test"` or a walk-forward id —
  this is what the OOS retest count (`analysis/oos_discipline.py`) reads
- `is_out_of_sample`: `True` only when the spec window is the quarantined
  test set
- `universe` / `data_snapshot` / `seed`: enough that someone else can re-run
  the trial

A failed trial is **still** a recorded trial. Do not silently drop a run
that errored — the executor logs it as `status="error"` and the reviewer
counts it. Hiding a failure is a worse offence than reporting one.

## Output format

Record each round as one JSON object (a line in `run/FACTOR_LOOP.jsonl`,
next to the ledger), no prose outside the JSON:

```json
{
  "intent": "select_factors | evaluate_round | decide_next",
  "payload": { ... }
}
```

Payload schemas:
`FactorSelection { factors: list[str], rationale: str }`,
`RoundEvaluation { verdict: good|mixed|poor, strongest_factor, weakest_factor,
notes }`, `LoopDecision { decision: continue|stop|expand_pool, next_subset?,
missing_dimension? }`.
