"""Tests for trader.pipeline.run_pipeline."""
from __future__ import annotations

import pandas as pd

from trader.config import StrategyConfig
from trader.pipeline import Snapshot, run_pipeline


def _build_snapshot(cache, universe, sectors, as_of):
    closes = {t: cache.slice_asof(t, as_of, lookback_days=400)["close"] for t in universe}
    dvol = {
        t: cache.slice_asof(t, as_of, lookback_days=400)["close"]
        * cache.slice_asof(t, as_of, lookback_days=400)["volume"]
        for t in universe
    }
    spy = cache.slice_asof("SPY", as_of, lookback_days=400)
    return Snapshot(
        as_of=as_of,
        closes=pd.DataFrame(closes).sort_index(),
        dollar_volume=pd.DataFrame(dvol).sort_index(),
        sectors=sectors,
        spy_history=spy["close"],
    )


def test_pipeline_returns_basket(cache, synth_universe, sectors):
    as_of = pd.Timestamp("2022-06-30")
    snap = _build_snapshot(cache, synth_universe, sectors, as_of)
    # Synth universe has 4 sectors, so picks=5 + cap=1 is structurally
    # impossible. Use cap=2 to allow a full basket of 5.
    config = StrategyConfig(picks=5, max_per_sector=2, backtest_mode=True)

    result = run_pipeline(snap, config)

    assert len(result.picks) == 5
    assert len(set(p.ticker for p in result.picks)) == 5
    sector_counts: dict[str, int] = {}
    for p in result.picks:
        sector_counts[p.sector] = sector_counts.get(p.sector, 0) + 1
    assert max(sector_counts.values()) <= 2


def test_pipeline_respects_sector_cap_with_enough_sectors(cache, synth_universe):
    as_of = pd.Timestamp("2022-06-30")
    # Give every ticker a unique sector so cap=1 is satisfiable.
    sectors = {t: f"Sector{i}" for i, t in enumerate(synth_universe)}
    snap = _build_snapshot(cache, synth_universe, sectors, as_of)
    config = StrategyConfig(picks=5, max_per_sector=1, backtest_mode=True)
    result = run_pipeline(snap, config)
    assert len(result.picks) == 5
    seen = [p.sector for p in result.picks]
    assert len(set(seen)) == 5


def test_pipeline_excludes_kill_listed(cache, synth_universe, sectors):
    as_of = pd.Timestamp("2022-06-30")
    snap = _build_snapshot(cache, synth_universe, sectors, as_of)
    config = StrategyConfig(picks=5, kill_list_tickers=frozenset({"AAA", "BBB"}),
                            backtest_mode=True)
    result = run_pipeline(snap, config)
    picked = {p.ticker for p in result.picks}
    assert not picked & {"AAA", "BBB"}
    assert "AAA" in result.excluded


def test_pipeline_warns_on_backtest_mode(cache, synth_universe, sectors):
    as_of = pd.Timestamp("2022-06-30")
    snap = _build_snapshot(cache, synth_universe, sectors, as_of)
    config = StrategyConfig(backtest_mode=True)
    result = run_pipeline(snap, config)
    assert any("DISABLED" in w for w in result.warnings)
