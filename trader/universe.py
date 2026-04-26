"""Universe construction.

v1 uses a static union of S&P 500 + Nasdaq 100 (current membership). This
introduces survivorship bias because we only see today's index members, not
historical ones. Every backtest run logs an explicit warning about this.
A `--universe` flag allows passing a custom list (e.g. from a paid Russell
1000 historical-membership snapshot).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Hand-curated current S&P 500 + Nasdaq 100 union.
# Kept small in v1 for offline tests; production users should override with
# `load_universe(path=...)` pointing at a CSV with one ticker per line.
DEFAULT_UNIVERSE: tuple[str, ...] = (
    # Mega-cap tech / NDX heavy hitters
    "AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO",
    "ADBE", "CSCO", "CRM", "INTC", "AMD", "QCOM", "TXN", "ORCL", "NFLX",
    "PYPL", "INTU", "BKNG", "PEP", "COST", "TMUS", "AMAT", "MU",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "AXP", "SCHW", "USB",
    # Health care
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY",
    # Industrials / consumer / energy / staples
    "BA", "CAT", "GE", "HON", "UPS", "RTX", "LMT", "DE", "MMM", "UNP",
    "WMT", "HD", "PG", "KO", "MCD", "NKE", "SBUX", "TGT", "LOW",
    "XOM", "CVX", "COP", "OXY", "SLB",
    # Comms / utilities / materials
    "T", "VZ", "CMCSA", "DIS",
    "DUK", "SO", "NEE",
    "LIN", "APD", "FCX", "NUE",
    # Misc large-caps that round things out
    "V", "MA", "SPGI", "ICE", "CME",
)


def load_universe(path: Optional[str | Path] = None, *, log_warning: bool = True) -> list[str]:
    """Return the trading universe.

    If `path` is provided, read tickers (one per line, '#' comments allowed)
    from that file. Otherwise fall back to `DEFAULT_UNIVERSE`. When the
    fallback is used and `log_warning` is set, emit a clear survivorship
    warning -- callers are responsible for surfacing it in reports.
    """
    if path is not None:
        text = Path(path).read_text()
        tickers = [
            line.split("#", 1)[0].strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return [t for t in tickers if t]

    if log_warning:
        logger.warning(
            "SURVIVORSHIP WARNING: using current S&P 500 + Nasdaq 100 union as the "
            "historical universe. Stocks that were delisted, acquired, or ejected "
            "from the index are absent, which biases historical returns upward. "
            "Pass --universe <file> with point-in-time membership to fix."
        )
    return list(DEFAULT_UNIVERSE)


def filter_to_priced(tickers: Iterable[str], prices: pd.DataFrame) -> list[str]:
    """Drop tickers that have no price data on the snapshot."""
    have = set(prices.columns)
    return [t for t in tickers if t in have]
