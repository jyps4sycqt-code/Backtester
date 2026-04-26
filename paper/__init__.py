"""Paper trader for the weekly basket strategy.

Wraps `trader.pipeline.run_pipeline` in a weekly cadence and submits the
resulting basket to a paper broker. Real-money execution is deliberately
NOT exposed -- callers must implement that themselves after paper trading
has validated the strategy.
"""

from paper.broker import Broker, BrokerOrder, BrokerPosition, OrderResult
from paper.dry_run import DryRunBroker
from paper.runner import PaperRun, PaperRunner

__all__ = [
    "Broker",
    "BrokerOrder",
    "BrokerPosition",
    "OrderResult",
    "DryRunBroker",
    "PaperRun",
    "PaperRunner",
]
