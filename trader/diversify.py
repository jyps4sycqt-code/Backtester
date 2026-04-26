"""Sector diversification.

Greedy selection: walk the ranked candidates from best composite downward,
admit a ticker if its sector hasn't already hit `max_per_sector`. Stops
when `picks` candidates have been chosen or the list is exhausted.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

import pandas as pd


def diversify(
    ranked: pd.DataFrame,
    sectors: Mapping[str, str],
    *,
    picks: int,
    max_per_sector: int = 1,
) -> pd.DataFrame:
    """Return a sector-diversified subset of `ranked`.

    `ranked` is a DataFrame indexed by ticker, sorted descending by score.
    `sectors` maps ticker -> sector string ("Unknown" is treated as its
    own bucket for capping purposes -- callers who want unknown to be
    unrestricted should map missing sectors to unique strings).
    """
    chosen: list[str] = []
    counts: dict[str, int] = defaultdict(int)

    for ticker in ranked.index:
        if len(chosen) >= picks:
            break
        sector = sectors.get(ticker, "Unknown")
        if counts[sector] >= max_per_sector:
            continue
        chosen.append(ticker)
        counts[sector] += 1

    return ranked.loc[chosen].copy()


def sectors_for_tickers(
    tickers: Iterable[str],
    sector_map: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Look up sectors with a fallback to "Unknown"."""
    sector_map = sector_map or {}
    return {t: sector_map.get(t, sector_map.get(t.upper(), "Unknown")) for t in tickers}
