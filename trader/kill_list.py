"""News kill list.

In v1 there is no live news feed wired up. This module provides:
- a static ticker exclusion set (`exclude_tickers`)
- a keyword scanner (`keyword_hits`) that callers can drive with whatever
  news headlines they have, returning the matched ticker -> keyword pairs

Both are pure functions so the backtest and paper trader use the same
exclusion logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class KillResult:
    excluded: frozenset[str]
    reasons: dict[str, str]   # ticker -> reason (matched keyword or "explicit")


def apply_kill_list(
    tickers: Iterable[str],
    *,
    explicit: Iterable[str] = (),
    headlines: Mapping[str, Iterable[str]] | None = None,
    keywords: Iterable[str] = (),
) -> KillResult:
    """Return the subset of tickers killed by either an explicit list or a
    keyword hit in their headlines.

    `headlines` maps ticker -> iterable of headline strings. Matching is
    case-insensitive substring. `keywords` is the configured kill phrases.
    """
    explicit_set = {t.upper() for t in explicit}
    keyword_list = [k.lower() for k in keywords]
    reasons: dict[str, str] = {}

    for t in tickers:
        upper = t.upper()
        if upper in explicit_set:
            reasons[upper] = "explicit"
            continue
        if not headlines or not keyword_list:
            continue
        ticker_news = headlines.get(upper) or headlines.get(t) or []
        for headline in ticker_news:
            text = headline.lower()
            for kw in keyword_list:
                if kw in text:
                    reasons[upper] = kw
                    break
            if upper in reasons:
                break

    return KillResult(excluded=frozenset(reasons), reasons=reasons)
