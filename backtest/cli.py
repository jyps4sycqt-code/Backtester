"""CLI for the backtester.

Usage:
    python -m backtest --start 2018-01-01 --end 2025-12-31
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from backtest.baseline import RandomBaseline
from backtest.report import write_report
from backtest.simulator import Simulator, SimulatorConfig
from trader.config import StrategyConfig
from trader.data import PriceCache, fetch_yfinance_into_cache
from trader.sectors import ensure_sectors
from trader.universe import load_universe

logger = logging.getLogger("backtest")


def _git_sha() -> Optional[str]:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return None


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="backtest", description="Replay the weekly basket strategy.")
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--end", default="2025-12-31")
    p.add_argument("--capital", type=float, default=1_000.0)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--universe", type=str, default=None, help="Path to a one-ticker-per-line universe file.")
    p.add_argument("--cache-dir", type=str, default="data/cache")
    p.add_argument("--sectors-file", type=str, default="data/sectors.json",
                   help="JSON cache of {ticker: sector}; built/refreshed when --fetch is set.")
    p.add_argument("--output-dir", type=str, default="results")
    p.add_argument("--in-sample-split", type=str, default="2022-12-31",
                   help="Last date considered in-sample (test starts the day after).")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--fetch", action="store_true",
                   help="Use yfinance to populate the cache for the universe.")
    p.add_argument("--skip-baseline", action="store_true")
    p.add_argument("--quiet", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cache = PriceCache(cache_dir=Path(args.cache_dir))
    universe = load_universe(args.universe, log_warning=args.universe is None)

    benchmarks_tickers = ["SPY", "QQQ", "RSP"]
    needed_for_fetch = list(set(universe + benchmarks_tickers))

    if args.fetch:
        logger.info("Fetching %d tickers via yfinance...", len(needed_for_fetch))
        fetch_yfinance_into_cache(needed_for_fetch, args.start, args.end, cache)

    have = [t for t in needed_for_fetch if cache.has(t)]
    if not have:
        logger.error("Cache is empty. Run with --fetch (requires yfinance + network).")
        return 2

    universe = [t for t in universe if cache.has(t)]
    if not universe:
        logger.error("No universe tickers in the cache.")
        return 2

    sectors = ensure_sectors(universe, args.sectors_file, fetch=args.fetch)
    if not sectors:
        logger.warning("No sectors loaded -- diversification cap will be a no-op.")
    else:
        unknown = sum(1 for v in sectors.values() if v == "Unknown")
        logger.info("Sectors: %d known, %d unknown across %d tickers",
                    len(sectors) - unknown, unknown, len(sectors))

    sim_config = SimulatorConfig(
        start=pd.Timestamp(args.start),
        end=pd.Timestamp(args.end),
        capital=args.capital,
        slippage_bps=args.slippage_bps,
        sectors=sectors,
        seed=args.seed,
    )
    strategy_config = StrategyConfig(capital=args.capital, backtest_mode=True)

    logger.info("Running strategy simulation...")
    sim = Simulator(cache, universe, sim_config, strategy_config).run()

    baseline_sim = None
    if not args.skip_baseline:
        logger.info("Running random baseline...")
        baseline_runner = RandomBaseline(seed=args.seed)
        baseline_sim = Simulator(
            cache, universe, sim_config, strategy_config,
            pipeline_fn=baseline_runner,
        ).run()

    benchmarks = {}
    for t in benchmarks_tickers:
        df = cache.get(t)
        if df is not None and not df.empty:
            benchmarks[t] = df["close"]

    config_summary = {
        "start": args.start,
        "end": args.end,
        "capital": args.capital,
        "slippage_bps": args.slippage_bps,
        "universe_size": len(universe),
        "universe_source": args.universe or "DEFAULT (SPX+NDX current, survivorship-biased)",
        "sectors_loaded": sum(1 for v in sectors.values() if v and v != "Unknown"),
        "picks": strategy_config.picks,
        "max_per_sector": strategy_config.max_per_sector,
        "use_fundamentals": strategy_config.use_fundamentals,
        "weights": strategy_config.weights,
        "seed": args.seed,
    }
    warnings = list({w for b in sim.baskets for w in b.pipeline_result.warnings})
    if args.universe is None:
        warnings.insert(0, "Universe is current SPX+NDX -- survivorship-biased.")

    in_sample_split = pd.Timestamp(args.in_sample_split) if args.in_sample_split else None

    report = write_report(
        output_dir=Path(args.output_dir),
        config_summary=config_summary,
        sim=sim,
        baseline_sim=baseline_sim,
        benchmarks=benchmarks,
        in_sample_split=in_sample_split,
        warnings=warnings,
        git_sha=_git_sha(),
    )
    logger.info("Wrote %s", report.path)
    print(report.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
