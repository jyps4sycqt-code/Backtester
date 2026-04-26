"""Cached price-history fetcher.

The cache lives at `data/cache/<ticker>.parquet` (overridable). Callers must
slice the resulting DataFrame to the as-of date themselves; this module
deliberately does NOT enforce point-in-time on read so that tests can load
a wide window once and slice it many times.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


@dataclass
class PriceCache:
    """A simple parquet-on-disk cache of OHLCV history per ticker."""

    cache_dir: Path = Path("data/cache")
    in_memory: dict[str, pd.DataFrame] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path(self, ticker: str) -> Path:
        return self.cache_dir / f"{ticker.upper()}.parquet"

    def has(self, ticker: str) -> bool:
        return ticker.upper() in self.in_memory or self.path(ticker).exists()

    def get(self, ticker: str) -> Optional[pd.DataFrame]:
        ticker = ticker.upper()
        if ticker in self.in_memory:
            return self.in_memory[ticker]
        p = self.path(ticker)
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        df = _normalize(df)
        self.in_memory[ticker] = df
        return df

    def put(self, ticker: str, df: pd.DataFrame) -> None:
        df = _normalize(df)
        self.in_memory[ticker.upper()] = df
        df.to_parquet(self.path(ticker))

    def slice_asof(self, ticker: str, end: pd.Timestamp, *, lookback_days: int = 400) -> Optional[pd.DataFrame]:
        """Return history strictly through `end`, last `lookback_days` rows."""
        df = self.get(ticker)
        if df is None or df.empty:
            return None
        end_ts = pd.Timestamp(end)
        if df.index.tz is not None and end_ts.tzinfo is None:
            end_ts = end_ts.tz_localize(df.index.tz)
        sliced = df.loc[df.index <= end_ts]
        if sliced.empty:
            return None
        return sliced.tail(lookback_days)


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"price frame missing columns: {missing}")
    return df[list(REQUIRED_COLUMNS)].astype(float)


def fetch_yfinance_into_cache(
    tickers: Iterable[str],
    start: str,
    end: str,
    cache: PriceCache,
) -> None:
    """Pull OHLCV via yfinance and store each ticker's frame in the cache."""
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise ImportError("yfinance not installed; `pip install yfinance`") from exc

    for ticker in tickers:
        try:
            raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)
        except Exception as exc:  # pragma: no cover - network
            logger.warning("yfinance failed for %s: %s", ticker, exc)
            continue
        if raw.empty:
            logger.warning("yfinance returned empty frame for %s", ticker)
            continue
        raw = raw.rename(
            columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )
        raw.index.name = "date"
        cache.put(ticker, raw[list(REQUIRED_COLUMNS)])


def build_close_panel(
    tickers: Iterable[str],
    cache: PriceCache,
    end: pd.Timestamp,
    lookback_days: int = 400,
) -> pd.DataFrame:
    """Wide panel of close prices: rows = dates, columns = tickers."""
    frames = {}
    for t in tickers:
        sliced = cache.slice_asof(t, end, lookback_days=lookback_days)
        if sliced is not None:
            frames[t] = sliced["close"]
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).sort_index()


def build_dollar_volume_panel(
    tickers: Iterable[str],
    cache: PriceCache,
    end: pd.Timestamp,
    lookback_days: int = 60,
) -> pd.DataFrame:
    frames = {}
    for t in tickers:
        sliced = cache.slice_asof(t, end, lookback_days=lookback_days)
        if sliced is not None:
            frames[t] = sliced["close"] * sliced["volume"]
    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).sort_index()
