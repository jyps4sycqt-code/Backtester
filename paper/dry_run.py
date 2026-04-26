"""Dry-run broker: writes intended trades to a JSONL log.

Useful for two things:
  1. CI / offline testing of the runner without any external service.
  2. A first-week sanity check: print what the live system *would* do
     before connecting to a real paper broker.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from paper.broker import BrokerOrder, BrokerPosition, OrderResult

logger = logging.getLogger(__name__)


@dataclass
class DryRunBroker:
    log_path: Path = Path("results/paper_dryrun.jsonl")
    starting_cash: float = 1_000.0
    positions: dict[str, BrokerPosition] = field(default_factory=dict)
    cash: float = field(init=False)
    _order_seq: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.log_path = Path(self.log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.cash = float(self.starting_cash)

    def name(self) -> str:
        return "dry-run"

    def get_cash(self) -> float:
        return self.cash

    def get_positions(self) -> list[BrokerPosition]:
        return [p for p in self.positions.values() if p.qty != 0]

    def _next_id(self) -> str:
        self._order_seq += 1
        return f"dry-{self._order_seq:06d}"

    def submit(self, order: BrokerOrder) -> OrderResult:
        order_id = self._next_id()
        self._log({"event": "submit", "id": order_id, **order.__dict__})
        return OrderResult(
            ticker=order.ticker,
            submitted_notional=order.notional,
            accepted=True,
            broker_order_id=order_id,
            fill_price=None,
            fill_qty=None,
            raw={"adapter": "dry-run"},
        )

    def liquidate(self, ticker: str) -> OrderResult:
        order_id = self._next_id()
        self._log({"event": "liquidate", "id": order_id, "ticker": ticker})
        self.positions.pop(ticker, None)
        return OrderResult(
            ticker=ticker, submitted_notional=0.0, accepted=True,
            broker_order_id=order_id, raw={"adapter": "dry-run"},
        )

    def _log(self, payload: dict) -> None:
        with self.log_path.open("a") as fh:
            fh.write(json.dumps(payload, default=str) + "\n")
        logger.info("dry-run %s", payload)
