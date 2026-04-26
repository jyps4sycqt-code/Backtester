"""Broker abstraction.

Implementations:
  - DryRunBroker (paper.dry_run): records intended trades to a JSONL file.
    No network. Default.
  - AlpacaPaperBroker (paper.alpaca): submits to Alpaca's paper API. Only
    activates if alpaca-py is installed AND ALPACA_API_KEY is set.

Real-money trading: NOT supported in this module by design. To go live,
implement a separate adapter and gate it behind an explicit env var
(`TRADER_LIVE_REAL_MONEY=1`) plus a confirmation prompt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class BrokerOrder:
    ticker: str
    notional: float          # USD; positive = buy, negative = sell
    selection_date: str
    note: str = ""


@dataclass
class OrderResult:
    ticker: str
    submitted_notional: float
    accepted: bool
    broker_order_id: str = ""
    fill_price: float | None = None
    fill_qty: float | None = None
    error: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class BrokerPosition:
    ticker: str
    qty: float
    avg_price: float
    market_value: float


class Broker(Protocol):
    """Minimal surface used by the paper runner."""

    def get_cash(self) -> float: ...

    def get_positions(self) -> list[BrokerPosition]: ...

    def submit(self, order: BrokerOrder) -> OrderResult: ...

    def liquidate(self, ticker: str) -> OrderResult: ...

    def name(self) -> str: ...
