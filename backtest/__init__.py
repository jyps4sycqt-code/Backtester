"""Backtest harness for the weekly basket strategy.

This module replays the SAME pipeline used by the paper trader (imported
from `trader.pipeline.run_pipeline`) against historical price data, then
produces a markdown summary, plots, and a `trades.parquet` log.
"""

from backtest.simulator import Simulator, SimulatorConfig, WeeklyBasket
from backtest.metrics import compute_stats, PerformanceStats

__all__ = [
    "Simulator",
    "SimulatorConfig",
    "WeeklyBasket",
    "compute_stats",
    "PerformanceStats",
]
