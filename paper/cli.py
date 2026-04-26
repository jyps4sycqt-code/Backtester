"""CLI for the paper trader.

Subcommands:
    python -m paper run --as-of 2026-04-24            # one-shot rebalance
    python -m paper run --as-of 2026-04-24 --dry      # log intentions only
    python -m paper status                            # show positions + cash
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from paper.broker import Broker
from paper.dry_run import DryRunBroker
from paper.runner import PaperRunner
from trader.config import StrategyConfig
from trader.data import PriceCache, fetch_yfinance_into_cache
from trader.earnings import ensure_earnings
from trader.sectors import ensure_sectors
from trader.universe import load_universe

logger = logging.getLogger("paper")


def _build_broker(adapter: str) -> Broker:
    if adapter == "dry-run":
        return DryRunBroker()
    if adapter == "alpaca":
        from paper.alpaca import AlpacaPaperBroker
        return AlpacaPaperBroker()
    raise ValueError(f"unknown broker adapter: {adapter}")


def _common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--cache-dir", default="data/cache")
    p.add_argument("--sectors-file", default="data/sectors.json")
    p.add_argument("--earnings-file", default="data/earnings.json")
    p.add_argument("--universe", default=None)
    p.add_argument("--broker", choices=("auto", "dry-run", "alpaca"), default="auto",
                   help="`auto` uses Alpaca if creds are set, else dry-run.")
    p.add_argument("--capital", type=float, default=1_000.0)
    p.add_argument("--quiet", action="store_true")


def _select_broker(adapter: str) -> Broker:
    if adapter == "auto":
        if os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_API_SECRET"):
            try:
                from paper.alpaca import AlpacaPaperBroker
                return AlpacaPaperBroker()
            except Exception as exc:
                logger.warning("Alpaca unavailable (%s); falling back to dry-run", exc)
        return DryRunBroker()
    return _build_broker(adapter)


def _cmd_run(args: argparse.Namespace) -> int:
    cache = PriceCache(cache_dir=Path(args.cache_dir))
    universe = load_universe(args.universe, log_warning=args.universe is None)

    if args.fetch:
        fetch_yfinance_into_cache(list(set(universe + ["SPY"])), args.fetch_start, args.as_of, cache)

    universe = [t for t in universe if cache.has(t)]
    if not universe:
        logger.error("Cache is empty for the configured universe. Run with --fetch.")
        return 2

    broker = _select_broker(args.broker)
    config = StrategyConfig(capital=args.capital)

    sectors = ensure_sectors(universe, args.sectors_file, fetch=args.fetch)
    earnings = ensure_earnings(universe, args.earnings_file, fetch=args.fetch)
    runner = PaperRunner(broker=broker, cache=cache, universe=universe,
                         config=config, sectors=sectors, earnings_dates=earnings)
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.utcnow().normalize()
    run = runner.run(as_of, dry=args.dry)
    print(run.summary())
    print(f"\nLog: {run.log_path}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    broker = _select_broker(args.broker)
    print(f"Broker:    {broker.name()}")
    print(f"Cash:      ${broker.get_cash():,.2f}")
    positions = broker.get_positions()
    if not positions:
        print("Positions: none")
    else:
        print("Positions:")
        for p in positions:
            print(f"  {p.ticker:<6}  qty={p.qty:>10.4f}  avg=${p.avg_price:>9.2f}  mv=${p.market_value:>10.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(prog="paper", description="Paper trade the weekly basket strategy.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Build a basket and submit to the broker.")
    _common_args(run_p)
    run_p.add_argument("--as-of", default=None, help="Selection date (default: today UTC).")
    run_p.add_argument("--dry", action="store_true", help="Log intended trades without submitting.")
    run_p.add_argument("--fetch", action="store_true", help="Refresh price cache via yfinance first.")
    run_p.add_argument("--fetch-start", default="2022-01-01")
    run_p.set_defaults(func=_cmd_run)

    status_p = sub.add_parser("status", help="Print broker cash + positions.")
    _common_args(status_p)
    status_p.set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
