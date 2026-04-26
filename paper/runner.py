"""Weekly cadence for the paper trader.

Workflow:
  1. Build a snapshot from the price cache (lookback ends at `as_of`).
  2. Call `trader.pipeline.run_pipeline` -- the SAME function the
     backtester uses -- to produce 5 picks.
  3. Liquidate any existing positions that are not in the new basket.
  4. Submit equal-dollar buy orders for the new picks.

This module does not schedule itself. Operators run it weekly via cron,
GitHub Actions, or manually:
    python -m paper run --as-of 2026-04-24
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from paper.broker import Broker, BrokerOrder
from trader.config import StrategyConfig
from trader.data import PriceCache
from trader.pipeline import PipelineResult, Snapshot, run_pipeline

logger = logging.getLogger(__name__)


@dataclass
class PaperRun:
    as_of: pd.Timestamp
    pipeline: PipelineResult
    rebalance_log: list[dict]
    cash_after: float
    log_path: Path

    def summary(self) -> str:
        lines = [
            f"Paper run @ {self.as_of.date()} (tier={self.pipeline.tier_used})",
            f"Cash after: ${self.cash_after:,.2f}",
            "Picks:",
        ]
        for p in self.pipeline.picks:
            lines.append(
                f"  {p.ticker:<6}  tier={p.tier}  sector={p.sector:<12}  "
                f"composite={p.composite:+.2f}  last=${p.last_price:,.2f}"
            )
        if not self.pipeline.picks:
            lines.append("  (none)")
        return "\n".join(lines)


@dataclass
class PaperRunner:
    broker: Broker
    cache: PriceCache
    universe: Sequence[str]
    config: StrategyConfig = field(default_factory=StrategyConfig)
    sectors: dict[str, str] = field(default_factory=dict)
    log_dir: Path = Path("results")

    def __post_init__(self) -> None:
        self.log_dir = Path(self.log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Paper runs always invoke the pipeline in non-backtest mode.
        self.config.backtest_mode = False

    def _build_snapshot(self, as_of: pd.Timestamp) -> Snapshot:
        closes, dvol = {}, {}
        for t in self.universe:
            sliced = self.cache.slice_asof(t, as_of, lookback_days=400)
            if sliced is None or sliced.empty:
                continue
            closes[t] = sliced["close"]
            dvol[t] = sliced["close"] * sliced["volume"]
        spy = self.cache.slice_asof("SPY", as_of, lookback_days=400)
        spy_hist = spy["close"] if spy is not None else None
        return Snapshot(
            as_of=as_of,
            closes=pd.DataFrame(closes).sort_index() if closes else pd.DataFrame(),
            dollar_volume=pd.DataFrame(dvol).sort_index() if dvol else pd.DataFrame(),
            sectors=self.sectors,
            spy_history=spy_hist,
        )

    def run(self, as_of: pd.Timestamp, *, dry: bool = False) -> PaperRun:
        as_of = pd.Timestamp(as_of)
        snapshot = self._build_snapshot(as_of)
        result = run_pipeline(snapshot, self.config)
        rebalance_log: list[dict] = []

        new_basket = {p.ticker.upper() for p in result.picks}
        held = {p.ticker.upper(): p for p in self.broker.get_positions()}

        # 1. Liquidate names dropped from the basket.
        for ticker in sorted(set(held) - new_basket):
            if dry:
                rebalance_log.append({"action": "would_liquidate", "ticker": ticker})
                continue
            res = self.broker.liquidate(ticker)
            rebalance_log.append({"action": "liquidate", "ticker": ticker,
                                  "accepted": res.accepted, "error": res.error})

        # 2. Buy new names equal-dollar.
        cash = self.broker.get_cash()
        per_name = (cash / max(self.config.picks, 1)) if result.picks else 0.0
        for pick in result.picks:
            if pick.ticker.upper() in held:
                rebalance_log.append({"action": "hold", "ticker": pick.ticker})
                continue
            order = BrokerOrder(
                ticker=pick.ticker,
                notional=per_name,
                selection_date=str(as_of.date()),
                note=f"tier={pick.tier} composite={pick.composite:+.3f}",
            )
            if dry:
                rebalance_log.append({"action": "would_buy", **order.__dict__})
                continue
            res = self.broker.submit(order)
            rebalance_log.append({"action": "buy", "ticker": pick.ticker,
                                  "notional": order.notional, "accepted": res.accepted,
                                  "order_id": res.broker_order_id, "error": res.error})

        # 3. Persist
        log_path = self.log_dir / f"paper_{as_of.date()}.json"
        log_path.write_text(json.dumps({
            "as_of": as_of.isoformat(),
            "broker": self.broker.name(),
            "tier_used": result.tier_used,
            "picks": result.to_records(),
            "rebalance": rebalance_log,
            "warnings": result.warnings,
        }, indent=2, default=str))

        return PaperRun(
            as_of=as_of,
            pipeline=result,
            rebalance_log=rebalance_log,
            cash_after=self.broker.get_cash(),
            log_path=log_path,
        )
