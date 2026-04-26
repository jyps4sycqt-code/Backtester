"""Simulator tests, including the no-look-ahead invariant."""
from __future__ import annotations

import pandas as pd

from backtest.simulator import Simulator, SimulatorConfig
from trader.config import StrategyConfig
from trader.pipeline import Snapshot


def test_simulator_runs_end_to_end(cache, synth_universe, sectors):
    sim_config = SimulatorConfig(
        start=pd.Timestamp("2020-01-01"),
        end=pd.Timestamp("2021-12-31"),
        capital=1_000.0,
        sectors=sectors,
    )
    strategy_config = StrategyConfig(picks=4, max_per_sector=1, backtest_mode=True)
    sim = Simulator(cache, synth_universe, sim_config, strategy_config).run()

    assert not sim.equity.empty
    assert sim.equity.iloc[0] == 1_000.0
    assert len(sim.baskets) > 40  # ~52 weeks/yr * 2 yrs
    assert not sim.trades.empty
    # All trades have entry < exit
    diffs = (sim.trades["exit_date"] - sim.trades["entry_date"]).dt.days
    assert (diffs >= 1).all()


def test_no_look_ahead_in_snapshot(cache, synth_universe, sectors):
    """The pipeline must never see prices after the selection date.

    We build a Snapshot the way the simulator does and assert every
    column's last index is <= as_of.
    """
    as_of = pd.Timestamp("2022-06-30")
    closes = {}
    dvol = {}
    for t in synth_universe:
        sliced = cache.slice_asof(t, as_of, lookback_days=400)
        closes[t] = sliced["close"]
        dvol[t] = sliced["close"] * sliced["volume"]
    snap = Snapshot(
        as_of=as_of,
        closes=pd.DataFrame(closes).sort_index(),
        dollar_volume=pd.DataFrame(dvol).sort_index(),
        sectors=sectors,
        spy_history=cache.slice_asof("SPY", as_of, lookback_days=400)["close"],
    )

    assert snap.closes.index.max() <= as_of
    assert snap.dollar_volume.index.max() <= as_of
    assert snap.spy_history.index.max() <= as_of


def test_capital_preserved_when_no_picks(cache, synth_universe):
    """If the universe has nothing, equity must equal starting capital."""
    sim_config = SimulatorConfig(
        start=pd.Timestamp("2020-01-01"),
        end=pd.Timestamp("2020-03-01"),
        capital=1_000.0,
    )
    # Pass empty universe -> no candidates -> no fills.
    strategy_config = StrategyConfig(backtest_mode=True)
    sim = Simulator(cache, [], sim_config, strategy_config).run()
    assert (sim.equity == 1_000.0).all()
    assert sim.trades.empty


def test_random_baseline_runs(cache, synth_universe, sectors):
    from backtest.baseline import RandomBaseline

    sim_config = SimulatorConfig(
        start=pd.Timestamp("2020-01-01"),
        end=pd.Timestamp("2020-12-31"),
        capital=1_000.0,
        sectors=sectors,
    )
    strategy_config = StrategyConfig(picks=4, max_per_sector=1, backtest_mode=True)

    sim_a = Simulator(cache, synth_universe, sim_config, strategy_config,
                      pipeline_fn=RandomBaseline(seed=1)).run()
    sim_b = Simulator(cache, synth_universe, sim_config, strategy_config,
                      pipeline_fn=RandomBaseline(seed=1)).run()

    # Same seed -> same equity curve.
    assert (sim_a.equity.values == sim_b.equity.values).all()
