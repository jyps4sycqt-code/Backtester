"""Random-baseline simulator: same gates, random selection.

This is the most important sanity check for the strategy. If composite
scoring doesn't beat random selection from the same gated pool by a
meaningful margin (Sharpe diff > ~0.3), the system is delivering market
beta and the composite is noise.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trader.config import StrategyConfig
from trader.candidates import build_candidates
from trader.diversify import diversify, sectors_for_tickers
from trader.kill_list import apply_kill_list
from trader.macro import read_macro
from trader.pipeline import Pick, PipelineResult, Snapshot


@dataclass
class RandomBaseline:
    seed: int = 0

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def __call__(self, snapshot: Snapshot, config: StrategyConfig) -> PipelineResult:
        """Mirrors `run_pipeline` but replaces composite scoring with shuffle."""
        as_of = pd.Timestamp(snapshot.as_of)
        macro = read_macro(as_of, snapshot.spy_history)

        if snapshot.closes.empty:
            return PipelineResult(
                as_of=as_of, picks=[], tier_used="none",
                macro=macro, excluded={}, config=config,
            )

        kill = apply_kill_list(
            snapshot.closes.columns,
            explicit=config.kill_list_tickers,
            headlines=snapshot.headlines,
            keywords=(),
        )

        candidates, tier_used = build_candidates(
            snapshot.closes, snapshot.dollar_volume,
            tiers=config.tiers, excluded=kill.excluded,
            min_picks=config.picks,
        )
        if candidates.empty:
            return PipelineResult(
                as_of=as_of, picks=[], tier_used=tier_used,
                macro=macro, excluded=dict(kill.reasons), config=config,
            )

        order = self._rng.permutation(len(candidates))
        ranked = candidates.iloc[order].copy()
        ranked["composite"] = np.linspace(1.0, -1.0, num=len(ranked))  # synthetic for ordering
        sectors = sectors_for_tickers(ranked.index, snapshot.sectors)
        final = diversify(ranked, sectors=sectors,
                          picks=config.picks, max_per_sector=config.max_per_sector)

        picks = [
            Pick(
                ticker=ticker,
                tier=int(final.at[ticker, "tier"]),
                sector=sectors.get(ticker, "Unknown"),
                composite=float(final.at[ticker, "composite"]),
                components={"random": float(final.at[ticker, "composite"])},
                last_price=float(final.at[ticker, "last_price"]),
            )
            for ticker in final.index
        ]
        return PipelineResult(
            as_of=as_of, picks=picks, tier_used=tier_used,
            macro=macro, excluded=dict(kill.reasons), config=config,
            candidate_pool_size=len(candidates),
            warnings=["Random baseline: composite scores are synthetic."],
        )
