"""Candlestick (K-line) charting for quant reports — OHLCV, with optional signals.

Renders a report-quality candlestick chart (moving averages + volume, an optional
signal panel and buy/sell markers) to a PNG, for reports and for *eyeballing what a
strategy is actually trading*. Uses mplfinance on a non-interactive ``Agg`` backend
so it runs headless. OHLCV comes from the task's own data as a pandas frame.
Import with this pack's folder on ``sys.path`` (``from charting import candlestick_chart``).
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np


def _prep(ohlcv: Any) -> Any:
    """Normalise an OHLCV frame to mplfinance's Title-case columns + datetime index."""
    import pandas as pd

    df = ohlcv.copy()
    ren = {c: str(c).lower().capitalize() for c in df.columns
           if str(c).lower() in ("open", "high", "low", "close", "volume")}
    df = df.rename(columns=ren)
    missing = [c for c in ("Open", "High", "Low", "Close") if c not in df.columns]
    if missing:
        raise ValueError(f"OHLCV frame missing columns {missing}")
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _style(convention: str = "cn"):
    """A clean mplfinance style. ``convention="cn"`` = A-share 红涨绿跌 (red up /
    green down); ``"us"`` = green up / red down. Also wires a CJK font so Chinese
    titles/labels render instead of tofu boxes.
    """
    import matplotlib.font_manager as fm
    import matplotlib.pyplot as plt
    import mplfinance as mpf

    have = {f.name for f in fm.fontManager.ttflist}
    for cand in ("Noto Sans CJK SC", "Noto Sans CJK JP", "WenQuanYi Micro Hei", "SimHei", "PingFang SC"):
        if cand in have:
            plt.rcParams["font.sans-serif"] = [cand, "DejaVu Sans"]
            plt.rcParams["axes.unicode_minus"] = False
            break
    up, down = ("red", "green") if convention == "cn" else ("green", "red")
    mc = mpf.make_marketcolors(up=up, down=down, edge="inherit", wick="inherit", volume="inherit")
    return mpf.make_mpf_style(
        base_mpf_style="charles", marketcolors=mc, gridstyle=":", gridcolor="#dcdcdc",
        facecolor="white", figcolor="white",
        rc={"axes.titlesize": 14, "axes.titleweight": "bold", "font.size": 11},
    )


def candlestick_chart(
    ohlcv: Any,
    out_path: str,
    *,
    title: str = "",
    mavs: Sequence[int] = (5, 20, 60),
    volume: bool = True,
    signal: Any = None,
    buy: Sequence[Any] | None = None,
    sell: Sequence[Any] | None = None,
    convention: str = "cn",
    figsize: tuple[float, float] = (15, 9),
) -> str:
    """Render a candlestick chart to ``out_path`` (PNG, parent folders made); returns the path.

    ``ohlcv``: DataFrame with open/high/low/close[/volume] (any case), date index.
    ``mavs``: moving-average windows overlaid on price. ``volume``: add a volume panel.
    ``signal``: optional Series (date -> value) drawn in a lower panel (e.g. a model
    score, so you can see the signal against the bars). ``buy``/``sell``: optional
    date lists marked with ▲/▼ on the price — to show where a strategy trades.
    ``convention="cn"`` renders A-share 红涨绿跌 (red up / green down).
    """
    import matplotlib
    matplotlib.use("Agg")
    import mplfinance as mpf
    import pandas as pd

    df = _prep(ohlcv)
    has_vol = bool(volume and "Volume" in df.columns)
    aps: list[Any] = []
    if signal is not None:
        s = pd.Series(signal).reindex(df.index)
        aps.append(mpf.make_addplot(s, panel=(2 if has_vol else 1), color="#7b3fa0", width=1.3, ylabel="signal"))

    def _markers(dates: Any, marker: str, color: str, up: bool):
        m = pd.Series(np.nan, index=df.index)
        if dates is not None and len(list(dates)):
            hit = df.index.intersection(pd.to_datetime(list(dates)))
            m.loc[hit] = df.loc[hit, "High" if up else "Low"] * (1.0 + (0.03 if up else -0.03))
        if m.notna().sum() == 0:
            return None
        return mpf.make_addplot(m, type="scatter", marker=marker, markersize=100, color=color)

    for ap in (_markers(buy, "^", "#d62728", up=False), _markers(sell, "v", "#2ca02c", up=True)):
        if ap is not None:
            aps.append(ap)

    plot_kwargs: dict[str, Any] = dict(
        type="candle", style=_style(convention), mav=tuple(mavs), volume=has_vol,
        title=title, figsize=figsize, tight_layout=True, scale_padding=0.4,
        mavcolors=["#1f77b4", "#ff7f0e", "#9467bd"],
        savefig=dict(fname=out_path, dpi=140, bbox_inches="tight"),
    )
    if aps:  # mplfinance rejects addplot=None; only pass it when non-empty
        plot_kwargs["addplot"] = aps
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    mpf.plot(df, **plot_kwargs)
    return out_path

