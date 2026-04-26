"""Synthetic-data fixtures for offline tests.

We deliberately avoid network: every test loads a deterministic price
panel built from a seeded random walk so the suite runs anywhere.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import pytest

from trader.data import PriceCache


def _gbm_path(n: int, mu: float, sigma: float, start: float, rng: np.random.Generator) -> np.ndarray:
    """Geometric brownian motion (daily) -> close-price path."""
    dt = 1 / 252
    drift = (mu - 0.5 * sigma ** 2) * dt
    shocks = rng.normal(0.0, sigma * np.sqrt(dt), size=n)
    log_returns = drift + shocks
    return start * np.exp(np.cumsum(log_returns))


def synthesize_ohlcv(
    tickers: Iterable[str],
    *,
    start: str = "2018-01-01",
    end: str = "2024-12-31",
    seed: int = 7,
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    n = len(dates)
    out: dict[str, pd.DataFrame] = {}
    for i, ticker in enumerate(tickers):
        # Slightly different drift / vol per ticker so the cross-section is non-trivial.
        mu = 0.06 + 0.04 * np.sin(i * 0.7)
        sigma = 0.20 + 0.05 * np.cos(i * 0.5)
        closes = _gbm_path(n, mu=mu, sigma=sigma, start=20 + (i % 11) * 5, rng=rng)
        # Build O/H/L around close with small intraday jitter.
        intraday = rng.normal(0.0, 0.005, size=(n, 3))
        opens = closes * (1.0 + intraday[:, 0])
        highs = np.maximum.reduce([closes, opens]) * (1.0 + np.abs(intraday[:, 1]))
        lows = np.minimum.reduce([closes, opens]) * (1.0 - np.abs(intraday[:, 2]))
        # Volume: lognormal so dollar volume varies.
        volume = rng.lognormal(mean=14.5 + (i % 7) * 0.3, sigma=0.3, size=n).astype(int)
        out[ticker] = pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": volume.astype(float),
            },
            index=pd.DatetimeIndex(dates, name="date"),
        )
    return out


@pytest.fixture
def synth_universe() -> list[str]:
    return [
        "AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH",
        "III", "JJJ", "KKK", "LLL", "MMM", "NNN", "OOO", "PPP",
    ]


@pytest.fixture
def synth_data(synth_universe) -> dict[str, pd.DataFrame]:
    return synthesize_ohlcv(synth_universe + ["SPY", "QQQ", "RSP"])


@pytest.fixture
def cache(tmp_path: Path, synth_data) -> PriceCache:
    c = PriceCache(cache_dir=tmp_path / "cache")
    for ticker, df in synth_data.items():
        c.put(ticker, df)
    return c


@pytest.fixture
def sectors(synth_universe) -> dict[str, str]:
    # Spread universe across 4 sectors so diversification has work to do.
    bins = ["Tech", "Health", "Industrial", "Energy"]
    return {t: bins[i % len(bins)] for i, t in enumerate(synth_universe)}
