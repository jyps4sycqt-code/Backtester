"""Tests for the sectors cache (offline -- no real yfinance call)."""
from __future__ import annotations

import json
from pathlib import Path

import trader.sectors as sectors_mod


def test_load_sectors_missing(tmp_path: Path):
    assert sectors_mod.load_sectors(tmp_path / "nope.json") == {}


def test_save_then_load_roundtrip(tmp_path: Path):
    path = tmp_path / "sectors.json"
    sectors_mod.save_sectors(path, {"AAPL": "Tech", "JNJ": "Health"})
    loaded = sectors_mod.load_sectors(path)
    assert loaded == {"AAPL": "Tech", "JNJ": "Health"}


def test_ensure_sectors_uses_cache_only(tmp_path: Path, monkeypatch):
    """When `fetch=False`, no network and no yfinance import."""
    path = tmp_path / "sectors.json"
    sectors_mod.save_sectors(path, {"AAPL": "Tech"})

    def boom(*a, **kw):
        raise AssertionError("fetch_sectors_yfinance should not be called when fetch=False")

    monkeypatch.setattr(sectors_mod, "fetch_sectors_yfinance", boom)
    out = sectors_mod.ensure_sectors(["AAPL", "JNJ"], path, fetch=False)
    assert out == {"AAPL": "Tech"}


def test_ensure_sectors_only_fetches_missing(tmp_path: Path, monkeypatch):
    path = tmp_path / "sectors.json"
    sectors_mod.save_sectors(path, {"AAPL": "Tech"})

    seen_args: list[list[str]] = []

    def fake_fetch(tickers, *, existing=None, sleep_s=0.0):
        seen_args.append(list(tickers))
        out = dict(existing or {})
        for t in tickers:
            out[t.upper()] = "FakeSector"
        return out

    monkeypatch.setattr(sectors_mod, "fetch_sectors_yfinance", fake_fetch)
    out = sectors_mod.ensure_sectors(["AAPL", "JNJ"], path, fetch=True)
    assert out["AAPL"] == "Tech"           # not refetched
    assert out["JNJ"] == "FakeSector"      # newly fetched
    assert seen_args == [["JNJ"]]
    # Cache file was rewritten with the merged set.
    on_disk = json.loads(path.read_text())
    assert set(on_disk) == {"AAPL", "JNJ"}
