"""Alpaca paper-trading adapter.

Activates only when `alpaca-py` is installed AND `ALPACA_API_KEY` /
`ALPACA_API_SECRET` are present in the environment. Otherwise importing
this module is fine, but constructing the broker will raise.

This is purposely a thin wrapper -- order placement uses notional dollar
amounts (so fractional shares "just work") and market orders only. Limit
orders, brackets, etc. can be added later if the strategy ever needs them.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from paper.broker import BrokerOrder, BrokerPosition, OrderResult

logger = logging.getLogger(__name__)


@dataclass
class AlpacaPaperBroker:
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://paper-api.alpaca.markets"

    _client: object | None = None

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("ALPACA_API_KEY", "")
        self.api_secret = self.api_secret or os.environ.get("ALPACA_API_SECRET", "")
        self.base_url = os.environ.get("ALPACA_BASE_URL", self.base_url)
        if not self.api_key or not self.api_secret:
            raise RuntimeError(
                "ALPACA_API_KEY / ALPACA_API_SECRET not set. "
                "Use DryRunBroker, or export Alpaca paper credentials."
            )
        if "paper" not in self.base_url:
            raise RuntimeError(
                f"Refusing to connect: base_url '{self.base_url}' is not the paper endpoint. "
                "Real-money trading is intentionally not supported by this adapter."
            )
        try:
            from alpaca.trading.client import TradingClient  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ImportError(
                "alpaca-py not installed. `pip install alpaca-py` (or omit this adapter)."
            ) from exc
        self._client = TradingClient(self.api_key, self.api_secret, paper=True)

    def name(self) -> str:
        return "alpaca-paper"

    def get_cash(self) -> float:
        account = self._client.get_account()  # type: ignore[union-attr]
        return float(account.cash)

    def get_positions(self) -> list[BrokerPosition]:
        positions = self._client.get_all_positions()  # type: ignore[union-attr]
        return [
            BrokerPosition(
                ticker=p.symbol,
                qty=float(p.qty),
                avg_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
            )
            for p in positions
        ]

    def submit(self, order: BrokerOrder) -> OrderResult:
        from alpaca.trading.requests import MarketOrderRequest  # type: ignore
        from alpaca.trading.enums import OrderSide, TimeInForce  # type: ignore

        side = OrderSide.BUY if order.notional > 0 else OrderSide.SELL
        notional = abs(order.notional)
        if notional <= 0:
            return OrderResult(ticker=order.ticker, submitted_notional=0.0,
                               accepted=False, error="zero notional")

        req = MarketOrderRequest(
            symbol=order.ticker,
            notional=round(notional, 2),
            side=side,
            time_in_force=TimeInForce.DAY,
        )
        try:
            resp = self._client.submit_order(req)  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover - network/auth errors
            return OrderResult(ticker=order.ticker, submitted_notional=order.notional,
                               accepted=False, error=str(exc))
        return OrderResult(
            ticker=order.ticker,
            submitted_notional=order.notional,
            accepted=True,
            broker_order_id=str(resp.id),
            raw={"status": str(resp.status)},
        )

    def liquidate(self, ticker: str) -> OrderResult:
        try:
            self._client.close_position(ticker)  # type: ignore[union-attr]
        except Exception as exc:  # pragma: no cover - network/auth errors
            return OrderResult(ticker=ticker, submitted_notional=0.0,
                               accepted=False, error=str(exc))
        return OrderResult(ticker=ticker, submitted_notional=0.0, accepted=True)


def maybe_build(prefer_alpaca: bool = True) -> Optional[AlpacaPaperBroker]:
    """Return an Alpaca broker if creds + library are available, else None."""
    if not prefer_alpaca:
        return None
    if not (os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_API_SECRET")):
        return None
    try:
        return AlpacaPaperBroker()
    except Exception as exc:
        logger.warning("Alpaca adapter unavailable: %s", exc)
        return None
