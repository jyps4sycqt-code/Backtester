"""Central configuration for the weekly basket strategy."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


# Sized for ~$1k starting capital across 5 names with fractional shares.
DEFAULT_CAPITAL = 1_000.0
DEFAULT_PICKS = 5
DEFAULT_PER_PICK = DEFAULT_CAPITAL / DEFAULT_PICKS  # $200 — close to live $196 sizing.

# Slippage applied per side in the backtest. 5 bps = 0.0005.
DEFAULT_SLIPPAGE_BPS = 5.0

# Liquidity / quality gates applied at tier 1.
TIER1_MIN_PRICE = 5.0
TIER1_MIN_DOLLAR_VOLUME = 5_000_000.0   # 20-day median in USD
TIER1_MIN_HISTORY_DAYS = 200             # need at least this much price history

# Composite score weights. Fundamentals are intentionally absent in v1
# (yfinance gives current-only values, which would inject look-ahead bias
# into the backtest). See pipeline.py for the warning emitted when this
# config is used in backtest mode.
COMPOSITE_WEIGHTS: dict[str, float] = {
    "momentum_6m": 0.30,
    "momentum_3m": 0.20,
    "trend": 0.20,
    "low_vol": 0.15,
    "short_reversal": 0.15,
}

# Tiered relaxation: progressively loosen gates until we have >=5 candidates.
@dataclass(frozen=True)
class Tier:
    name: str
    min_price: float
    min_dollar_volume: float
    min_history_days: int


TIERS: Tuple[Tier, ...] = (
    Tier("tier1_strict", 5.0, 5_000_000.0, 200),
    Tier("tier2_relaxed_volume", 5.0, 1_000_000.0, 200),
    Tier("tier3_relaxed_price", 2.0, 1_000_000.0, 150),
    Tier("tier4_relaxed_history", 2.0, 500_000.0, 100),
    Tier("tier5_anything", 1.0, 100_000.0, 60),
)


# Sector cap for the final basket: at most this many picks per sector.
MAX_PER_SECTOR = 1

# Keyword-based news kill list. In v1 there is no news feed wired up;
# tickers explicitly listed in `KILL_LIST_TICKERS` are excluded, and
# `KILL_LIST_KEYWORDS` is plumbed through for when a feed is added.
KILL_LIST_TICKERS: frozenset[str] = frozenset()
KILL_LIST_KEYWORDS: tuple[str, ...] = (
    "bankruptcy",
    "going concern",
    "restating",
    "delisting",
    "fraud",
    "sec investigation",
    "accounting irregularities",
)


@dataclass
class StrategyConfig:
    """Knobs for a single backtest or paper-trading run."""

    capital: float = DEFAULT_CAPITAL
    picks: int = DEFAULT_PICKS
    weights: dict[str, float] = field(default_factory=lambda: dict(COMPOSITE_WEIGHTS))
    tiers: Tuple[Tier, ...] = TIERS
    max_per_sector: int = MAX_PER_SECTOR
    kill_list_tickers: frozenset[str] = KILL_LIST_TICKERS
    use_fundamentals: bool = False  # v1: always False
    backtest_mode: bool = False     # set True by the backtester for warnings
