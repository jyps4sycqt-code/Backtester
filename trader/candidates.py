"""Candidate construction and tiered relaxation.

`build_candidates` runs the configured tiers in order, accumulating
qualifying tickers, and stops at the first tier that yields enough
names to fill the basket. Each ticker carries the tier number it
qualified under so the final report can attribute returns to tiers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from trader.config import Tier


@dataclass(frozen=True)
class Candidate:
    ticker: str
    tier: int
    last_price: float
    dollar_volume_20d: float
    history_days: int


def _ticker_metrics(closes: pd.DataFrame, dollar_vol: pd.DataFrame) -> pd.DataFrame:
    last_price = closes.ffill().iloc[-1]
    if dollar_vol.empty:
        adv = pd.Series(np.nan, index=closes.columns)
    else:
        adv = dollar_vol.tail(20).median()
    history_days = closes.notna().sum()
    return pd.DataFrame(
        {
            "last_price": last_price,
            "dollar_volume_20d": adv.reindex(last_price.index),
            "history_days": history_days,
        }
    )


def build_candidates(
    closes: pd.DataFrame,
    dollar_vol: pd.DataFrame,
    tiers: Sequence[Tier],
    *,
    excluded: Iterable[str] = (),
    min_picks: int = 5,
) -> tuple[pd.DataFrame, str]:
    """Apply tiered relaxation and return (candidate_table, tier_used).

    The returned DataFrame has columns: tier, last_price, dollar_volume_20d,
    history_days, indexed by ticker.
    """
    metrics = _ticker_metrics(closes, dollar_vol)
    excluded = {t.upper() for t in excluded}
    metrics = metrics.loc[~metrics.index.str.upper().isin(excluded)]

    accumulated: dict[str, int] = {}
    last_tier = tiers[-1].name

    for i, tier in enumerate(tiers, start=1):
        ok = (
            (metrics["last_price"] >= tier.min_price)
            & (metrics["dollar_volume_20d"] >= tier.min_dollar_volume)
            & (metrics["history_days"] >= tier.min_history_days)
        )
        for ticker in metrics.index[ok.fillna(False)]:
            accumulated.setdefault(ticker, i)

        if len(accumulated) >= min_picks:
            last_tier = tier.name
            break
        last_tier = tier.name

    if not accumulated:
        return pd.DataFrame(columns=["tier", "last_price", "dollar_volume_20d", "history_days"]), last_tier

    rows = []
    for ticker, tier_idx in accumulated.items():
        row = metrics.loc[ticker].to_dict()
        row["tier"] = tier_idx
        row["ticker"] = ticker
        rows.append(row)
    out = pd.DataFrame(rows).set_index("ticker")
    return out[["tier", "last_price", "dollar_volume_20d", "history_days"]], last_tier
