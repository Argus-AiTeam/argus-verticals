---
name: quant
description: "equity factor research (IC/ICIR, backtest, Sharpe) producing a reviewer-certified report, not a generic metric loop"
version: 0.2.0
---

# quant

equity factor research (IC/ICIR, backtest, Sharpe) producing a reviewer-certified report, not a generic metric loop.

## What counts as done

### research

- **research.hypotheses** — Each factor hypothesis states an economic / market-mechanism rationale for why it should predict future returns, and an expected sign — written BEFORE any backtest, grounded in literature or documented market structure.
  Evidence hint: research/FACTOR_HYPOTHESES.json

- **research.hypothesis_priors** — The rationale, expected direction, and rejection conditions for each hypothesis are fixed before testing, so a later result cannot retro-justify a factor that had no prior thesis.
  Evidence hint: research/HYPOTHESIS_PRIORS.json

- **research.prior_art** — Known/existing factors this hypothesis overlaps with are identified up front, so novelty and redundancy versus the standard factor zoo are understood before testing.
  Evidence hint: research/PRIOR_FACTORS.tsv

### plan

- **plan.data_pit_provenance** — Data sources, timestamps, point-in-time / revision handling, corporate-action adjustment policy, and universe construction are disclosed; inputs are as-known-at-decision-time, not restated or back-filled.
  Evidence hint: plan/DATA_PROVENANCE.md

- **plan.eval_protocol** — The train/validation/test split (or walk-forward windows) is fixed in advance, the test set is quarantined, and the rule for when (and how many times) it may be touched is stated.
  Evidence hint: plan/EVAL_PROTOCOL.json

- **plan.cost_model_predeclared** — Transaction-cost, slippage, and turnover-cost assumptions are declared BEFORE screening, with source/justification, so costs cannot be tuned after seeing results.
  Evidence hint: plan/COST_MODEL.json

- **plan.metrics** — The evaluation metrics and the thresholds a factor must clear (IC/RankIC, ICIR, long-short return, turnover, cost-adjusted return, etc.) are decided in advance, not chosen after seeing which ones look best.
  Evidence hint: plan/METRICS.json

### benchmark

- **benchmark.no_lookahead** — The backtest harness is verified free of look-ahead: the factor at time t uses only information available at t, and future returns t -> t+h are aligned to the factor without leaking future data into the signal.
  Evidence hint: benchmark/LEAKAGE_CHECKS.md

- **benchmark.universe_bias_free** — The investable universe is survivorship- and selection-bias controlled: delisted / dead names are included as-of-date, and membership is reconstructed point-in-time.
  Evidence hint: benchmark/UNIVERSE_AUDIT.md

- **benchmark.baseline** — At least one baseline / benchmark (a known factor and/or the market) is wired in, so new factors are judged on incremental value rather than in a vacuum.
  Evidence hint: benchmark/BASELINE.json

- **benchmark.harness_authentic** — The backtest engine runs end-to-end on a known sanity case and reproduces an expected result, proving the substrate is trustworthy before any broad search begins.
  Evidence hint: benchmark/SANITY_RUN.md

### run

- **run.search_ledger_complete** — Every backtest trial attempted (factor, combination, weighting, window, params) is appended to the search ledger at execution time — including failures and discards — so the full search breadth can be checked and cherry-picking is visible.
  Evidence hint: run/SEARCH_LEDGER.jsonl — check it with `python3 '<this folder>/search_ledger.py' verify --path run/SEARCH_LEDGER.jsonl`; a row deleted from or inserted into the middle, or rows reordered, break the index sequence and fail. The check says whether the rows are well-formed and in sequence, not whether the search was broad enough.

- **run.screening** — Factor screening over the library applies the pre-declared metrics/thresholds; the screen criteria and the surviving factors are recorded.
  Evidence hint: run/SCREEN_RESULTS.tsv

- **run.combinations** — Combinations are built explicitly (equal-weight and/or optimized-weight), with the weighting method and any optimization inputs recorded per combination.
  Evidence hint: run/COMBINATIONS.json

- **run.cost_model_applied** — The pre-declared cost model is actually applied in every reported backtest: all headline returns are net of transaction costs and slippage.
  Evidence hint: run/SEARCH_LEDGER.jsonl

### analysis

- **analysis.evidence** — Each surviving factor/combination is characterized with the full evidence set: IC/RankIC, ICIR, quantile monotonicity, long-short return, turnover, and cost-adjusted return.
  Evidence hint: analysis/FACTOR_EVIDENCE.json

- **analysis.test_set_quarantine** — Reported headline performance is out-of-sample under the fixed protocol: the test set was not iteratively tuned on, and any retest / peeking is disclosed in the ledger and the metric downgraded accordingly.
  Evidence hint: analysis/OOS_REPORT.md

- **analysis.multiple_testing** — Data-mining / multiple-testing risk is quantified from the search-ledger breadth (e.g. deflated metric, haircut, or FDR control); headline numbers are discounted for the number of trials run.
  Evidence hint: analysis/MULTIPLE_TESTING.md

- **analysis.independence** — Each selected factor's incremental value over known factors is shown (orthogonalization / correlation to the existing factor set), so the alpha is not a repackaged known factor.
  Evidence hint: analysis/ORTHOGONALITY.tsv

- **analysis.claims** — Every quantitative claim the report will make is bound to its raw backtest rows in the search ledger and to the figure/table that will show it.
  Evidence hint: analysis/CLAIM_GRAPH.json

### draft

- **draft.report** — The factor report states, for each selected factor/combination, WHY it was chosen — the economic interpretation plus the supporting evidence — not merely its performance numbers.
  Evidence hint: report/FACTOR_REPORT.md

- **draft.limitations** — The report discloses limitations and risks: regime dependence, capacity / liquidity, alpha decay, crowding, and the search breadth behind the result.
  Evidence hint: report/FACTOR_REPORT.md

- **draft.figures** — Headline evidence (IC over time, quantile curves, long-short equity, OOS-vs-IS) is presented as figures/tables grounded in the files the analysis stage produced.
  Evidence hint: report/figures/

### review

- **review.interpretability** — Every selected factor carries a coherent economic interpretation; none is kept purely because it backtests well with no plausible mechanism.
  Evidence hint: report/FACTOR_REPORT.md

- **review.evidence_grounded** — Every number in the report traces to a search-ledger row or a file from the analysis stage; no figure or claim is un-sourced or a placeholder.
  Evidence hint: report/FACTOR_REPORT.md

- **review.search_disclosed** — The report honestly discloses the search breadth (how many factors / combinations were tried) and the multiple-testing adjustment, so a referee can judge cherry-picking.
  Evidence hint: report/FACTOR_REPORT.md, run/SEARCH_LEDGER.jsonl

### submission

- **submission.reproducible** — The report is reproducible: data snapshot/version, code/config version, random seeds, and the complete search ledger are included so an independent reviewer can re-run the work and check every number.
  Evidence hint: report/REPRO_MANIFEST.json

- **submission.ledger_complete** — The disclosed search ledger is the complete one used: the trial counts match the search breadth the report claims.
  Evidence hint: report/REPRO_MANIFEST.json, run/SEARCH_LEDGER.jsonl

- **submission.assurance** — A final assurance statement certifies no look-ahead, point-in-time data, out-of-sample results, costs applied, and full search disclosed.
  Evidence hint: report/ASSURANCE.md

## Run the checks

Run from the project workspace; replace `<this folder>` with this pack's absolute directory:

```sh
python3 '<this folder>/search_ledger.py' --help
python3 '<this folder>/search_ledger.py' verify --path run/SEARCH_LEDGER.jsonl
python3 '<this folder>/search_ledger.py' verify --path run/SEARCH_LEDGER.jsonl --json
```

The ledger is JSONL, one `{index, recorded_at, payload}` object per trial, written by [backtest.py](backtest.py) (`run_backtest` / `ForcingExecutor.submit`) and by `model_toolkit.select_model`; do not write rows by hand. Exit 0 prints `search-ledger: OK, N trial row(s)`: every line parses and the indices run 0, 1, 2, ... Exit 1 means the file is missing, a row was deleted or inserted mid-file or rows reordered (`OUT OF SEQUENCE`), or a line is not a ledger row (`NOT A LEDGER`); exit 2 is bad usage. `--json` prints `{path, exists, valid, rows}` instead. The check shows structure and the trial count only: an edited payload, a dropped last row, too narrow a search, missing costs or OOS peeking are not detected, so compare the rows the report cites with the trial outputs and use the analysis helpers below.

## Needs

Python 3.10+. search_ledger.py and backtest.py use only the standard library; analysis/ needs `numpy>=1.26` (`scipy>=1.11` optional: `ic_half_life` falls back to a two-point fit without it); model_toolkit/ needs numpy and `pandas>=2`, plus `lightgbm>=4` for the `gbdt` family, `torch>=2.2` for `mlp` (GPU when available, CPU otherwise) and `scikit-learn>=1.4` for the `linear` ridge baseline; charting.py needs pandas, `matplotlib>=3.8` and `mplfinance>=0.12.10b0`. The research itself needs the task's point-in-time equity data (prices, corporate actions, delisted names, universe membership) and a backtest engine for it; no license or special hardware. Nothing is installed or detected by this pack.

## Role references

Each entry is a bundled file; project output paths within the references are created by the task.

- engineer: [kline-chart.md](skills/engineer/kline-chart.md)

- engineer: [model-selection-loop.md](skills/engineer/model-selection-loop.md)

- engineer: [quant-factor-loop.md](skills/engineer/quant-factor-loop.md)

- reviewer: [quant-factor-report-review.md](skills/reviewer/quant-factor-report-review.md)


## Supporting files

The Python files are helpers for project code; import them with this folder on `sys.path` (`import sys; sys.path.insert(0, '<this folder>')`, then e.g. `from backtest import ForcingExecutor`), and do not give project modules the same names (`backtest`, `search_ledger`, `charting`, `analysis`, `model_toolkit`).

- [LICENSE](LICENSE)

- [search_ledger.py](search_ledger.py) — `SearchLedger(path)`: append-only trial ledger (`append`, `rows`, `gap`) and the check above.

- [backtest.py](backtest.py) — `BacktestSpec`, `BacktestResult`, the `BacktestEngine` protocol your engine implements, and `ForcingExecutor(engine, ledger).submit(spec)`, which writes every trial, failures included, to the ledger (run.search_ledger_complete; put the applied cost model in `BacktestResult.metadata` for run.cost_model_applied).

- [analysis/__init__.py](analysis/__init__.py)

- [analysis/walk_forward.py](analysis/walk_forward.py) — purged, embargoed walk-forward folds (plan.eval_protocol).

- [analysis/factor_overfit.py](analysis/factor_overfit.py) — per-period IC, IC stability, regime stress, placebo permutation test and IC half-life; `factor_overfit_report` runs all four (analysis.evidence).

- [analysis/oos_discipline.py](analysis/oos_discipline.py) — `retest_counts(SearchLedger(path).rows())`: how often each factor was run in each window and whether that window is out-of-sample, most-retested first (analysis.test_set_quarantine).

- [analysis/multiple_testing.py](analysis/multiple_testing.py) — deflated Sharpe ratio, Sharpe haircut, Benjamini-Hochberg FDR and effective number of trials (analysis.multiple_testing).

- [analysis/orthogonality.py](analysis/orthogonality.py) — factor correlation matrix and incremental variance share over known factors (analysis.independence).

- [model_toolkit/__init__.py](model_toolkit/__init__.py)

- [model_toolkit/registry.py](model_toolkit/registry.py) — `ModelSpec` and the default model space.

- [model_toolkit/task_profile.py](model_toolkit/task_profile.py) — task profile and the prior ordering of the model space.

- [model_toolkit/trainers.py](model_toolkit/trainers.py) — `gbdt`, `mlp` and `linear` trainers built from a config.

- [model_toolkit/selection.py](model_toolkit/selection.py) — `select_model`: nested walk-forward with successive halving, every candidate × fold ledgered.

- [charting.py](charting.py) — `candlestick_chart` for K-line report figures (draft.figures).
