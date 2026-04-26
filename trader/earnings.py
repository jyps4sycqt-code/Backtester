"""Earnings-date lookup with on-disk JSON cache.

Used to drop names whose next earnings announcement falls inside the
holding window. Earnings drops or beats routinely move stocks 5-15% in
a single session, which is larger than a typical week's expected return,
so holding through an earnings event adds idiosyncratic variance the
backtest doesn't model well.

yfinance is the only free source we have. `Ticker.calendar` returns
the *next* earnings date (sometimes a list, sometimes a single date,
sometimes empty depending on data availability). We cache the answer
per ticker as an ISO date string and refetch when the cached date is in
the past.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _to_iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]
    if isinstance(value, str):
        try:
            return pd.Timestamp(value).date().isoformat()
        except Exception:
            return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return pd.Timestamp(value).date().isoformat()
    return None


def load_earnings(path: str | Path) -> dict[str, Optional[str]]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        logger.warning("Failed to parse earnings cache %s: %s", p, exc)
        return {}


def save_earnings(path: str | Path, earnings: Mapping[str, Optional[str]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(sorted(earnings.items())), indent=2, default=str))


def _next_from_earnings_dates(tk, today_iso: str) -> Optional[str]:
    """Try Ticker.earnings_dates, the most reliable yfinance earnings source."""
    try:
        df = tk.earnings_dates
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    try:
        # Index is a DatetimeIndex (sometimes tz-aware). Pick smallest future entry.
        idx = pd.to_datetime(df.index).tz_localize(None) if df.index.tz is not None else pd.to_datetime(df.index)
        future = sorted(d for d in idx if d.date().isoformat() >= today_iso)
        if future:
            return future[0].date().isoformat()
    except Exception:
        return None
    return None


def _next_from_calendar(tk) -> Optional[str]:
    try:
        cal = tk.calendar
    except Exception:
        return None
    if isinstance(cal, dict):
        return _to_iso(cal.get("Earnings Date") or cal.get("earningsDate"))
    if isinstance(cal, pd.DataFrame) and not cal.empty:
        try:
            if "Earnings Date" in cal.index:
                return _to_iso(cal.loc["Earnings Date"].iloc[0])
        except Exception:
            return None
    return None


def _next_from_info(tk) -> Optional[str]:
    try:
        info = tk.info or {}
    except Exception:
        return None
    ts = info.get("earningsTimestamp") or info.get("earningsTimestampStart")
    if not ts:
        return None
    try:
        return pd.Timestamp(int(ts), unit="s").date().isoformat()
    except Exception:
        return None


def fetch_earnings_yfinance(
    tickers: Iterable[str],
    *,
    existing: Mapping[str, Optional[str]] | None = None,
) -> dict[str, Optional[str]]:
    """Look up next-earnings-date for each ticker via yfinance.

    Tries three sources in order:
      1. Ticker.earnings_dates   (DataFrame; pick smallest future date)
      2. Ticker.calendar         (dict or DataFrame; older API)
      3. Ticker.info             (earningsTimestamp unix epoch)

    Refetches tickers whose cached date is missing or in the past.
    None means yfinance had no usable data for the ticker.
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise ImportError("yfinance not installed; `pip install yfinance`") from exc

    out: dict[str, Optional[str]] = {k.upper(): v for k, v in (existing or {}).items()}
    today_iso = pd.Timestamp.now(tz="UTC").date().isoformat()

    for ticker in tickers:
        upper = ticker.upper()
        cached = out.get(upper)
        if cached is not None and cached >= today_iso:
            continue
        try:
            tk = yf.Ticker(ticker)
        except Exception as exc:  # pragma: no cover - network
            logger.warning("earnings lookup failed for %s: %s", ticker, exc)
            out[upper] = None
            continue

        next_date = (
            _next_from_earnings_dates(tk, today_iso)
            or _next_from_calendar(tk)
            or _next_from_info(tk)
        )
        out[upper] = next_date

    return out


def ensure_earnings(
    tickers: Iterable[str],
    cache_path: str | Path,
    *,
    fetch: bool = True,
) -> dict[str, Optional[str]]:
    existing = load_earnings(cache_path)
    if not fetch:
        return existing
    merged = fetch_earnings_yfinance(tickers, existing=existing)
    save_earnings(cache_path, merged)
    return merged


def tickers_reporting_in(
    earnings: Mapping[str, Optional[str]],
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, str]:
    """Return {ticker: earnings_date_iso} for names whose earnings fall in [start, end] (inclusive)."""
    start_d = pd.Timestamp(start).date()
    end_d = pd.Timestamp(end).date()
    out: dict[str, str] = {}
    for ticker, iso in earnings.items():
        if not iso:
            continue
        try:
            d = pd.Timestamp(iso).date()
        except Exception:
            continue
        if start_d <= d <= end_d:
            out[ticker.upper()] = iso
    return out
