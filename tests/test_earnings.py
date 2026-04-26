"""Earnings filter tests (offline)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import trader.earnings as earnings_mod
from trader.config import StrategyConfig
from trader.pipeline import Snapshot, run_pipeline


def test_load_save_earnings_roundtrip(tmp_path: Path):
    p = tmp_path / "e.json"
    earnings_mod.save_earnings(p, {"AAPL": "2026-05-01", "JNJ": None})
    loaded = earnings_mod.load_earnings(p)
    assert loaded == {"AAPL": "2026-05-01", "JNJ": None}


def test_tickers_reporting_in_window():
    earnings = {
        "AAPL": "2026-05-01",
        "MSFT": "2026-05-15",
        "JNJ": None,
        "TSLA": "2026-04-30",
    }
    out = earnings_mod.tickers_reporting_in(
        earnings,
        pd.Timestamp("2026-04-27"),
        pd.Timestamp("2026-05-04"),
    )
    assert set(out) == {"AAPL", "TSLA"}
    assert "MSFT" not in out  # outside window
    assert "JNJ" not in out   # no earnings date


def test_ensure_earnings_fetch_false(tmp_path: Path, monkeypatch):
    p = tmp_path / "e.json"
    earnings_mod.save_earnings(p, {"AAPL": "2026-05-01"})

    def boom(*a, **kw):
        raise AssertionError("fetch should not be called")

    monkeypatch.setattr(earnings_mod, "fetch_earnings_yfinance", boom)
    out = earnings_mod.ensure_earnings(["AAPL", "MSFT"], p, fetch=False)
    assert out == {"AAPL": "2026-05-01"}


def test_pipeline_excludes_earnings_in_window(cache, synth_universe, sectors):
    """Names with earnings inside the hold window are dropped from the pipeline."""
    as_of = pd.Timestamp("2022-06-30")
    closes = {t: cache.slice_asof(t, as_of, lookback_days=400)["close"] for t in synth_universe}
    dvol = {
        t: cache.slice_asof(t, as_of, lookback_days=400)["close"]
        * cache.slice_asof(t, as_of, lookback_days=400)["volume"]
        for t in synth_universe
    }
    spy = cache.slice_asof("SPY", as_of, lookback_days=400)

    # Pretend AAA, BBB, CCC report earnings inside the holding window.
    in_window = {"AAA": "2022-07-04", "BBB": "2022-07-05", "CCC": "2022-07-06"}

    snap = Snapshot(
        as_of=as_of,
        closes=pd.DataFrame(closes).sort_index(),
        dollar_volume=pd.DataFrame(dvol).sort_index(),
        sectors=sectors,
        spy_history=spy["close"],
        earnings_in_window=in_window,
    )
    config = StrategyConfig(picks=5, max_per_sector=2, backtest_mode=True)
    result = run_pipeline(snap, config)

    picked = {p.ticker for p in result.picks}
    assert not picked & set(in_window)
    for ticker, iso in in_window.items():
        assert ticker in result.excluded
        assert "earnings" in result.excluded[ticker]
