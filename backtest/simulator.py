"""Backtest simulator: weekly rebalance loop.

Mechanics:
  - Selection at the bar of the *Friday close* using only data with
    timestamp <= that Friday (no look-ahead).
  - Execution at the *next available* trading-day open (Monday, or the
    next session if Monday is a holiday).
  - Hold exactly one week: enter on Mon t open, exit on Mon t+1 open.
  - Equal-dollar across `picks`. Fractional shares allowed. Slippage
    applied to entry and exit (5 bps default). Zero commission.
  - Cash drag: if the pipeline returns fewer than `picks` names, the
    unfilled portion sits in cash at 0%.

The simulator imports `trader.pipeline.run_pipeline` -- the SAME function
the paper trader uses -- to satisfy the "reuse, don't reimplement" rule.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from trader.config import StrategyConfig
from trader.data import PriceCache
from trader.pipeline import PipelineResult, Snapshot, run_pipeline

logger = logging.getLogger(__name__)


@dataclass
class SimulatorConfig:
    start: pd.Timestamp
    end: pd.Timestamp
    capital: float = 1_000.0
    slippage_bps: float = 5.0
    sectors: dict[str, str] = field(default_factory=dict)
    spy_ticker: str = "SPY"
    seed: int = 0


@dataclass
class WeeklyBasket:
    selection_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    pipeline_result: PipelineResult
    fills: list[dict]
    weekly_return: float
    equity_after: float


def _trading_dates(closes: pd.DataFrame) -> pd.DatetimeIndex:
    return closes.dropna(how="all").index


def _next_trading_day(idx: pd.DatetimeIndex, after: pd.Timestamp) -> Optional[pd.Timestamp]:
    pos = idx.searchsorted(after, side="right")
    if pos >= len(idx):
        return None
    return idx[pos]


def _fridays(idx: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    """Friday-close sampling dates within [start, end] from the trading calendar.

    For each calendar week we pick the LATEST trading day on or before Friday
    (handles half-days and Friday holidays cleanly).
    """
    in_range = idx[(idx >= start) & (idx <= end)]
    if in_range.empty:
        return []
    week = pd.Series(in_range, index=in_range).groupby(in_range.to_period("W-FRI"))
    return [week.get_group(k).iloc[-1] for k in week.groups]


def _build_snapshot(
    selection_date: pd.Timestamp,
    cache: PriceCache,
    universe: Sequence[str],
    sectors: dict[str, str],
    spy_ticker: str,
    config: StrategyConfig,
) -> Snapshot:
    closes = {}
    dvol = {}
    for t in universe:
        sliced = cache.slice_asof(t, selection_date, lookback_days=400)
        if sliced is None or sliced.empty:
            continue
        closes[t] = sliced["close"]
        dvol[t] = sliced["close"] * sliced["volume"]
    closes_df = pd.DataFrame(closes).sort_index() if closes else pd.DataFrame()
    dvol_df = pd.DataFrame(dvol).sort_index() if dvol else pd.DataFrame()

    spy_hist = None
    spy_df = cache.slice_asof(spy_ticker, selection_date, lookback_days=400)
    if spy_df is not None:
        spy_hist = spy_df["close"]

    return Snapshot(
        as_of=selection_date,
        closes=closes_df,
        dollar_volume=dvol_df,
        sectors=sectors,
        spy_history=spy_hist,
        headlines=None,
    )


@dataclass
class SimulationOutput:
    equity: pd.Series                # weekly equity curve indexed by exit date
    baskets: list[WeeklyBasket]
    trades: pd.DataFrame             # one row per fill (entry and exit each)
    selection_dates: list[pd.Timestamp]


class Simulator:
    """Driver class. Construct with a price cache + config, then `.run()`."""

    def __init__(
        self,
        cache: PriceCache,
        universe: Sequence[str],
        sim_config: SimulatorConfig,
        strategy_config: Optional[StrategyConfig] = None,
        pipeline_fn=run_pipeline,
    ) -> None:
        self.cache = cache
        self.universe = list(universe)
        self.sim_config = sim_config
        self.strategy_config = strategy_config or StrategyConfig(backtest_mode=True)
        self.strategy_config.backtest_mode = True
        self.pipeline_fn = pipeline_fn

    def _calendar(self) -> pd.DatetimeIndex:
        # Use SPY (or first present) as the canonical trading calendar.
        spy = self.cache.get(self.sim_config.spy_ticker)
        if spy is not None and not spy.empty:
            return spy.index
        for t in self.universe:
            df = self.cache.get(t)
            if df is not None and not df.empty:
                return df.index
        return pd.DatetimeIndex([])

    def run(self) -> SimulationOutput:
        cal = self._calendar()
        if cal.empty:
            raise ValueError("Calendar is empty: load some price data into the cache first.")

        slip = self.sim_config.slippage_bps / 10_000.0
        fridays = _fridays(cal, self.sim_config.start, self.sim_config.end)

        equity = self.sim_config.capital
        equity_curve: list[tuple[pd.Timestamp, float]] = []
        baskets: list[WeeklyBasket] = []
        trade_rows: list[dict] = []

        for friday in fridays:
            entry = _next_trading_day(cal, friday)
            if entry is None:
                break
            exit_date = _next_trading_day(cal, entry + pd.Timedelta(days=4))
            if exit_date is None:
                break

            snap = _build_snapshot(
                friday, self.cache, self.universe,
                self.sim_config.sectors, self.sim_config.spy_ticker,
                self.strategy_config,
            )
            result = self.pipeline_fn(snap, self.strategy_config)

            n_picks = len(result.picks) or self.strategy_config.picks
            per_name_dollars = equity / self.strategy_config.picks  # cash drag if fewer picks
            invested = 0.0
            week_pnl = 0.0
            fills_for_basket: list[dict] = []

            for pick in result.picks:
                hist = self.cache.slice_asof(pick.ticker, exit_date, lookback_days=10)
                if hist is None or hist.empty:
                    continue
                # Entry: open of `entry` date.
                if entry not in hist.index:
                    continue
                entry_open = float(hist.loc[entry, "open"])
                entry_price = entry_open * (1.0 + slip)

                if exit_date not in hist.index:
                    continue
                exit_open = float(hist.loc[exit_date, "open"])
                exit_price = exit_open * (1.0 - slip)

                shares = per_name_dollars / entry_price if entry_price > 0 else 0.0
                position_pnl = shares * (exit_price - entry_price)
                week_pnl += position_pnl
                invested += per_name_dollars

                trade = {
                    "selection_date": friday,
                    "entry_date": entry,
                    "exit_date": exit_date,
                    "ticker": pick.ticker,
                    "sector": pick.sector,
                    "tier": pick.tier,
                    "composite": pick.composite,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "shares": shares,
                    "position_pnl": position_pnl,
                    "weight": per_name_dollars / equity if equity else 0.0,
                }
                trade.update({f"component_{k}": v for k, v in pick.components.items()})
                trade_rows.append(trade)
                fills_for_basket.append(trade)

            new_equity = equity + week_pnl
            weekly_return = (new_equity - equity) / equity if equity else 0.0
            equity = new_equity
            equity_curve.append((exit_date, equity))
            baskets.append(
                WeeklyBasket(
                    selection_date=friday,
                    entry_date=entry,
                    exit_date=exit_date,
                    pipeline_result=result,
                    fills=fills_for_basket,
                    weekly_return=weekly_return,
                    equity_after=equity,
                )
            )

        if not equity_curve:
            equity_series = pd.Series([self.sim_config.capital], index=pd.DatetimeIndex([self.sim_config.start], name="date"), name="equity")
        else:
            idx = pd.DatetimeIndex([d for d, _ in equity_curve], name="date")
            vals = [v for _, v in equity_curve]
            equity_series = pd.Series([self.sim_config.capital] + vals,
                                      index=pd.DatetimeIndex([fridays[0]] + list(idx), name="date"),
                                      name="equity")

        trades_df = pd.DataFrame(trade_rows)
        return SimulationOutput(
            equity=equity_series,
            baskets=baskets,
            trades=trades_df,
            selection_dates=list(fridays),
        )
