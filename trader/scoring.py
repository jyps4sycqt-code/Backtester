"""Composite scoring components.

Each component returns a Series indexed by ticker with values in roughly
the same order of magnitude (we cross-sectionally rank-normalize before
combining, which makes them comparable). All inputs are point-in-time:
`closes` must be a wide DataFrame whose last row is the as-of bar.
"""
from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


def _safe_pct_change(closes: pd.DataFrame, lookback: int) -> pd.Series:
    """Return the % change over `lookback` trading days; NaN if insufficient data."""
    if len(closes) <= lookback:
        return pd.Series(np.nan, index=closes.columns)
    end = closes.iloc[-1]
    start = closes.iloc[-lookback - 1]
    return (end / start - 1.0).astype(float)


def momentum(closes: pd.DataFrame, lookback: int) -> pd.Series:
    return _safe_pct_change(closes, lookback)


def trend(closes: pd.DataFrame, fast: int = 50, slow: int = 200) -> pd.Series:
    """Distance of fast SMA above slow SMA, scaled by slow SMA."""
    if len(closes) < slow + 1:
        return pd.Series(np.nan, index=closes.columns)
    fast_sma = closes.iloc[-fast:].mean()
    slow_sma = closes.iloc[-slow:].mean()
    return ((fast_sma - slow_sma) / slow_sma).astype(float)


def low_vol(closes: pd.DataFrame, lookback: int = 63) -> pd.Series:
    """Negative of realized vol so higher is better."""
    if len(closes) < lookback + 1:
        return pd.Series(np.nan, index=closes.columns)
    rets = closes.iloc[-lookback - 1 :].pct_change().dropna()
    if rets.empty:
        return pd.Series(np.nan, index=closes.columns)
    return (-rets.std(ddof=0) * np.sqrt(252)).astype(float)


def short_reversal(closes: pd.DataFrame, lookback: int = 21) -> pd.Series:
    """Negative of recent return: oversold names score higher."""
    chg = _safe_pct_change(closes, lookback)
    return -chg


def cross_sectional_zscore(series: pd.Series) -> pd.Series:
    """Z-score across tickers, ignoring NaNs."""
    s = series.astype(float)
    valid = s.dropna()
    if valid.empty:
        return s
    mean = valid.mean()
    std = valid.std(ddof=0)
    if std == 0 or np.isnan(std):
        return pd.Series(0.0, index=s.index)
    return (s - mean) / std


def composite_score(
    closes: pd.DataFrame,
    weights: Mapping[str, float],
) -> pd.DataFrame:
    """Compute per-ticker component scores and a weighted composite.

    Returns a DataFrame indexed by ticker with columns:
        momentum_6m, momentum_3m, trend, low_vol, short_reversal, composite
    Tickers with insufficient history get NaN composites and will be
    filtered by the candidate stage.
    """
    components = {
        "momentum_6m": momentum(closes, lookback=126),
        "momentum_3m": momentum(closes, lookback=63),
        "trend": trend(closes),
        "low_vol": low_vol(closes),
        "short_reversal": short_reversal(closes),
    }
    df = pd.DataFrame(components)
    z = df.apply(cross_sectional_zscore)
    composite = sum(z[k] * float(w) for k, w in weights.items() if k in z.columns)
    df["composite"] = composite
    return df
