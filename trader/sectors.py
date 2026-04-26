"""Sector lookup with on-disk JSON cache.

The diversifier needs a `ticker -> sector` mapping. yfinance exposes it
via `Ticker(symbol).info["sector"]`, but `.info` is slow and rate-limited,
so we cache results to a JSON file and only refetch missing tickers.

Sectors aren't point-in-time — a company's sector today might not match
its sector five years ago. For weekly rotation that's an acceptable
approximation; flagging here so it's not forgotten.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


def load_sectors(path: str | Path) -> dict[str, str]:
    """Load `{ticker: sector}` from a JSON cache file (empty if missing)."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as exc:
        logger.warning("Failed to parse sectors cache %s: %s", p, exc)
        return {}


def save_sectors(path: str | Path, sectors: dict[str, str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(dict(sorted(sectors.items())), indent=2))


def fetch_sectors_yfinance(
    tickers: Iterable[str],
    *,
    existing: dict[str, str] | None = None,
    sleep_s: float = 0.0,
) -> dict[str, str]:
    """Look up sectors via yfinance for tickers not already in `existing`.

    Returns the merged mapping. Missing/failed lookups are recorded as
    "Unknown" so we don't refetch them every run.
    """
    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dep
        raise ImportError("yfinance not installed; `pip install yfinance`") from exc

    out = dict(existing or {})
    todo = [t for t in tickers if t.upper() not in {k.upper() for k in out}]
    for ticker in todo:
        try:
            info = yf.Ticker(ticker).info or {}
            sector = info.get("sector") or info.get("sectorKey") or "Unknown"
        except Exception as exc:  # pragma: no cover - network
            logger.warning("sector lookup failed for %s: %s", ticker, exc)
            sector = "Unknown"
        out[ticker.upper()] = sector
        if sleep_s:
            import time
            time.sleep(sleep_s)
    return out


def ensure_sectors(
    tickers: Iterable[str],
    cache_path: str | Path,
    *,
    fetch: bool = True,
) -> dict[str, str]:
    """Load the sector cache and (optionally) fetch any missing tickers.

    The result is the merged mapping, and the cache file is updated on disk
    if any new sectors were fetched.
    """
    existing = load_sectors(cache_path)
    have = {k.upper() for k in existing}
    missing = [t for t in tickers if t.upper() not in have]
    if not missing or not fetch:
        return existing
    logger.info("Fetching sectors for %d ticker(s) via yfinance...", len(missing))
    merged = fetch_sectors_yfinance(missing, existing=existing)
    save_sectors(cache_path, merged)
    return merged
