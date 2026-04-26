"""Weekly basket rotation strategy: shared pipeline.

Everything in this package is pure: functions take a date and a data
snapshot and return values. They are imported and called by both
`backtest/` (historical replay) and `paper/` (live cadence). If the two
ever diverge in selection logic, the backtest is worthless -- so do not
duplicate this code anywhere else.
"""

from trader.pipeline import PipelineResult, Pick, run_pipeline

__all__ = ["PipelineResult", "Pick", "run_pipeline"]
__version__ = "0.1.0"
