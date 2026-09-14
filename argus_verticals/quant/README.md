# quant

**Purpose:** equity factor research (IC/ICIR, backtest, Sharpe) producing a reviewer-certified report, not a generic metric loop.

Research-kind mission with a `certified` completion gate. Only `stages.py` is imported when Argus loads the vertical; the toolkits import numpy/pandas and friends lazily or on their own import.

- `stages.py`: stage order, checklists, protected checklist items.
- `search_ledger.py`: hash-chained trial ledger with a CLI (`python -m argus_verticals.quant.search_ledger`).
- `backtest.py`, `executor.py`, `factors.py`, `reference_engine.py`, `leakage_probe.py`, `portfolio.py`, `charting.py`: the backtest contract, forced-ledger executor, factor registry, numpy-only reference engine, look-ahead probe, portfolio construction, K-line charts.
- `analysis/`: walk-forward splits, multiple-testing accounting, orthogonality, out-of-sample discipline, overfit diagnostics.
- `factor_toolkit/`, `model_toolkit/`: expression DSL, feature builders, evolutionary search, model registry and disciplined selection.
- `integrations/`: `qlib_cn`, `adata_cn`, `finance_argus`, `backtrader`, `vectorbt` adapters; each imports its vendor package lazily.
- `skills/engineer/`, `skills/reviewer/`.

Extras: `quant` (numpy, pandas, scipy, scikit-learn, matplotlib, mplfinance, lightgbm, torch). `qlib`, `adata`, `backtrader`, `vectorbt`, and the private `finance_argus` package are not packaged. Tests: `tests/test_quant_*.py`; those needing lightgbm, torch, qlib, or adata skip when absent.

Manifest: `vertical.json` (store metadata; the purpose line above is read from `stages.py`).
