"""Performance metrics computed from a weekly equity curve.

The strategy rebalances weekly, so returns are at weekly frequency.
Annualization uses 52 weeks/year.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


PERIODS_PER_YEAR = 52


@dataclass
class PerformanceStats:
    total_return: float
    cagr: float
    annualized_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_weeks: int
    time_to_recovery_weeks: Optional[int]
    calmar_ratio: float
    weekly_win_rate: Optional[float]
    avg_win_week: Optional[float]
    avg_loss_week: Optional[float]
    n_weeks: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def max_drawdown(equity: pd.Series) -> tuple[float, int, Optional[int]]:
    """Return (max drawdown, weeks underwater at trough, weeks-to-recovery)."""
    if equity.empty:
        return 0.0, 0, None
    peak = equity.cummax()
    dd = equity / peak - 1.0
    trough_idx = dd.idxmin()
    mdd = float(dd.loc[trough_idx])
    if mdd == 0.0:
        return 0.0, 0, 0

    peak_pos = int(np.argmax(equity.loc[:trough_idx].values))
    trough_pos = int(equity.index.get_loc(trough_idx))
    duration = trough_pos - peak_pos

    peak_value = equity.iloc[peak_pos]
    after = equity.iloc[trough_pos:]
    recovered = after[after >= peak_value]
    if recovered.empty:
        ttr = None
    else:
        ttr = int(equity.index.get_loc(recovered.index[0]) - peak_pos)

    return mdd, duration, ttr


def compute_stats(equity: pd.Series) -> PerformanceStats:
    """Compute weekly-frequency performance stats from an equity curve."""
    if equity.empty or len(equity) < 2:
        return PerformanceStats(0, 0, 0, 0, 0, 0, 0, None, 0, None, None, None, len(equity))

    returns = equity.pct_change().dropna()
    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = max(len(returns) / PERIODS_PER_YEAR, 1e-9)
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0) if equity.iloc[0] > 0 else 0.0

    vol = float(returns.std(ddof=0) * np.sqrt(PERIODS_PER_YEAR))
    sharpe = float(returns.mean() / returns.std(ddof=0) * np.sqrt(PERIODS_PER_YEAR)) if returns.std(ddof=0) > 0 else 0.0
    downside = returns[returns < 0]
    dstd = float(downside.std(ddof=0)) if not downside.empty else 0.0
    sortino = float(returns.mean() / dstd * np.sqrt(PERIODS_PER_YEAR)) if dstd > 0 else 0.0

    mdd, mdd_weeks, ttr = max_drawdown(equity)
    calmar = float(cagr / abs(mdd)) if mdd < 0 else 0.0

    wins = returns[returns > 0]
    losses = returns[returns < 0]
    win_rate = float(len(wins) / len(returns)) if len(returns) else None
    avg_win = float(wins.mean()) if not wins.empty else None
    avg_loss = float(losses.mean()) if not losses.empty else None

    return PerformanceStats(
        total_return=total_return,
        cagr=cagr,
        annualized_volatility=vol,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=mdd,
        max_drawdown_weeks=mdd_weeks,
        time_to_recovery_weeks=ttr,
        calmar_ratio=calmar,
        weekly_win_rate=win_rate,
        avg_win_week=avg_win,
        avg_loss_week=avg_loss,
        n_weeks=len(equity),
    )


def benchmark_stats(closes: pd.Series, weekly_index: pd.DatetimeIndex) -> PerformanceStats:
    """Equity stats for a buy-and-hold benchmark, sampled at the weekly grid."""
    closes = closes.dropna()
    if closes.empty:
        return PerformanceStats(0, 0, 0, 0, 0, 0, 0, None, 0, None, None, None, 0)
    aligned = closes.reindex(weekly_index, method="ffill").dropna()
    if aligned.empty:
        return PerformanceStats(0, 0, 0, 0, 0, 0, 0, None, 0, None, None, None, 0)
    equity = aligned / aligned.iloc[0]
    return compute_stats(equity)
