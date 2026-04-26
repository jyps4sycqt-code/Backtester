"""Tests for performance metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.metrics import compute_stats, max_drawdown


def test_max_drawdown_basic():
    eq = pd.Series([100, 120, 110, 90, 95, 130], index=pd.date_range("2024-01-01", periods=6, freq="W"))
    mdd, weeks, ttr = max_drawdown(eq)
    assert mdd < 0
    assert abs(mdd - (90 / 120 - 1.0)) < 1e-9
    assert weeks >= 1
    assert ttr is not None


def test_compute_stats_zero_returns():
    eq = pd.Series([100.0] * 10, index=pd.date_range("2024-01-01", periods=10, freq="W"))
    s = compute_stats(eq)
    assert s.total_return == 0.0
    assert s.sharpe_ratio == 0.0
    assert s.max_drawdown == 0.0


def test_compute_stats_monotonic_up():
    eq = pd.Series(np.linspace(100, 200, 53), index=pd.date_range("2024-01-01", periods=53, freq="W"))
    s = compute_stats(eq)
    assert s.total_return > 0.99
    assert s.sharpe_ratio > 0
    assert s.max_drawdown == 0.0
