"""Macro / regime read.

v1 keeps this minimal: a binary risk-on/off flag based on whether SPY's
close is above its 200-day moving average on the as-of date. The flag is
returned in `MacroState` and may be consumed by `pipeline.run_pipeline`
(today it's reported but does not gate selection -- wire-in point for
later). This is intentionally simple; production would add yield curve,
credit spreads, vol regime, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class MacroState:
    as_of: pd.Timestamp
    risk_on: bool
    spy_close: Optional[float]
    spy_sma200: Optional[float]

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat(),
            "risk_on": self.risk_on,
            "spy_close": self.spy_close,
            "spy_sma200": self.spy_sma200,
        }


def read_macro(as_of: pd.Timestamp, spy_history: Optional[pd.Series]) -> MacroState:
    """Compute the macro regime from SPY close history through `as_of`.

    `spy_history` is a Series of SPY closes indexed by date. It must contain
    only data with timestamp <= as_of (caller's responsibility).
    """
    if spy_history is None or spy_history.empty:
        return MacroState(as_of=pd.Timestamp(as_of), risk_on=True, spy_close=None, spy_sma200=None)

    spy_close = float(spy_history.iloc[-1])
    if len(spy_history) >= 200:
        sma200 = float(spy_history.iloc[-200:].mean())
    else:
        sma200 = float(spy_history.mean())
    return MacroState(
        as_of=pd.Timestamp(as_of),
        risk_on=spy_close >= sma200,
        spy_close=spy_close,
        spy_sma200=sma200,
    )
