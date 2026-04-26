"""End-to-end pipeline: snapshot -> 5 picks.

This is the SINGLE source of truth for selection logic. Both backtest
replay and live/paper trading call `run_pipeline` with the same signature.
Any divergence between backtest and live MUST be fixed by changing this
function, not by reimplementing it in a caller.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping, Optional

import pandas as pd

from trader.candidates import build_candidates
from trader.config import StrategyConfig
from trader.diversify import diversify, sectors_for_tickers
from trader.kill_list import apply_kill_list
from trader.macro import MacroState, read_macro
from trader.scoring import composite_score

logger = logging.getLogger(__name__)


@dataclass
class Pick:
    ticker: str
    tier: int
    sector: str
    composite: float
    components: dict[str, float]
    last_price: float


@dataclass
class PipelineResult:
    as_of: pd.Timestamp
    picks: list[Pick]
    tier_used: str
    macro: MacroState
    excluded: dict[str, str]
    config: StrategyConfig
    candidate_pool_size: int = 0
    warnings: list[str] = field(default_factory=list)

    def tickers(self) -> list[str]:
        return [p.ticker for p in self.picks]

    def to_records(self) -> list[dict]:
        out = []
        for p in self.picks:
            row = {
                "ticker": p.ticker,
                "tier": p.tier,
                "sector": p.sector,
                "composite": p.composite,
                "last_price": p.last_price,
            }
            row.update({f"component_{k}": v for k, v in p.components.items()})
            out.append(row)
        return out


@dataclass
class Snapshot:
    """All as-of-`as_of` data the pipeline needs.

    Callers (backtester, paper trader) build this from cached / live data
    and guarantee no rows after `as_of`.
    """

    as_of: pd.Timestamp
    closes: pd.DataFrame                  # wide: rows=dates, cols=tickers (close prices)
    dollar_volume: pd.DataFrame           # same shape, dollar volume
    sectors: Mapping[str, str]            # ticker -> sector string
    spy_history: Optional[pd.Series] = None
    headlines: Optional[Mapping[str, list[str]]] = None  # ticker -> headline strings


def run_pipeline(snapshot: Snapshot, config: StrategyConfig) -> PipelineResult:
    """Run the 7-stage pipeline and return at most `config.picks` names."""
    as_of = pd.Timestamp(snapshot.as_of)
    warnings: list[str] = []

    if config.backtest_mode and config.use_fundamentals:
        warnings.append(
            "Fundamentals weighting is enabled in backtest mode. yfinance returns "
            "current-only fundamentals which will inject look-ahead bias."
        )
    if config.backtest_mode and not config.use_fundamentals:
        warnings.append(
            "Fundamentals weighting is DISABLED in backtest mode (v1 default) -- "
            "backtest composite uses momentum/trend/vol/reversal only."
        )

    macro = read_macro(as_of, snapshot.spy_history)

    closes = snapshot.closes
    if closes.empty:
        return PipelineResult(
            as_of=as_of, picks=[], tier_used="none",
            macro=macro, excluded={}, config=config, warnings=warnings,
        )

    # 1. Apply kill list to the universe before doing the scoring work.
    kill = apply_kill_list(
        closes.columns,
        explicit=config.kill_list_tickers,
        headlines=snapshot.headlines,
        keywords=(),
    )

    # 2. Tiered candidate construction.
    candidates, tier_used = build_candidates(
        closes,
        snapshot.dollar_volume,
        tiers=config.tiers,
        excluded=kill.excluded,
        min_picks=config.picks,
    )

    if candidates.empty:
        warnings.append("No candidates survived even the most relaxed tier.")
        return PipelineResult(
            as_of=as_of, picks=[], tier_used=tier_used,
            macro=macro, excluded=dict(kill.reasons), config=config, warnings=warnings,
        )

    # 3. Score the surviving candidates.
    cand_closes = closes[candidates.index.tolist()]
    scores = composite_score(cand_closes, weights=config.weights)
    scores = scores.reindex(candidates.index)
    scores = scores.dropna(subset=["composite"])
    if scores.empty:
        warnings.append("All candidates had NaN composites (insufficient history).")
        return PipelineResult(
            as_of=as_of, picks=[], tier_used=tier_used,
            macro=macro, excluded=dict(kill.reasons), config=config,
            candidate_pool_size=len(candidates), warnings=warnings,
        )

    ranked = scores.sort_values("composite", ascending=False)
    ranked = ranked.join(candidates[["tier", "last_price"]], how="left")

    # 4. Sector diversification.
    sectors = sectors_for_tickers(ranked.index, snapshot.sectors)
    final = diversify(
        ranked,
        sectors=sectors,
        picks=config.picks,
        max_per_sector=config.max_per_sector,
    )

    # 5. Build the picks.
    picks: list[Pick] = []
    component_cols = [c for c in scores.columns if c != "composite"]
    for ticker in final.index:
        components = {c: float(scores.at[ticker, c]) for c in component_cols if pd.notna(scores.at[ticker, c])}
        picks.append(
            Pick(
                ticker=ticker,
                tier=int(final.at[ticker, "tier"]),
                sector=sectors.get(ticker, "Unknown"),
                composite=float(final.at[ticker, "composite"]),
                components=components,
                last_price=float(final.at[ticker, "last_price"]),
            )
        )

    return PipelineResult(
        as_of=as_of,
        picks=picks,
        tier_used=tier_used,
        macro=macro,
        excluded=dict(kill.reasons),
        config=config,
        candidate_pool_size=len(candidates),
        warnings=warnings,
    )
