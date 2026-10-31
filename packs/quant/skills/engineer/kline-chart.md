---
name: "K-line Chart Skill (Engineer)"
description: "Render candlestick (K-line) charts from OHLCV — moving averages, volume, and (optionally) the model signal / buy-sell markers overlaid — for quant reports and for eyeballing what a strategy actually trades. Backed by this pack's charting.py (mplfinance, headless Agg)."
---

## Title
K-line Chart Skill (Engineer)

## Description
Use this when a quant mission needs to **show**, not just describe, price action or
what a strategy is doing — a report figure, a sanity look at a name, or a picture of
where a signal says to buy/sell. Renders a report-quality candlestick chart to a PNG.

## API ([charting.py](../../charting.py))
- `candlestick_chart(ohlcv, out_path, *, title, mavs=(5,20,60), volume=True, signal=None, buy=None, sell=None)`
  — `ohlcv` is a DataFrame with open/high/low/close[/volume] (any case), date index,
  loaded from the task's own data. `signal` (a date→value Series) draws in a lower
  panel; `buy`/`sell` (date lists) mark ▲/▼ on the price.

## Guidance
- **Always overlay the signal / trades when the point is the strategy.** A bare
  candlestick describes the market; `signal=`/`buy=`/`sell=` shows what the *model*
  is doing against it — that is the figure a reviewer/user actually learns from.
- Title every chart with the instrument + window (e.g. `"SH600519 2025-06..2026-06"`).
- Save the PNG under the project's `report/figures/` and reference the path in the report.
- Headless-safe (Agg backend); never blocks on a display.

## Example
```python
import sys; sys.path.insert(0, "<this folder>")  # the quant pack's folder
from charting import candlestick_chart
candlestick_chart(ohlcv.loc["2025-06-01":"2026-06-04"], "report/figures/moutai.png",
                  title="SH600519 2025-06..2026-06", mavs=(5, 20, 60),
                  buy=buy_dates, sell=sell_dates, signal=score_series)
```
