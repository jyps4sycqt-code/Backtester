#!/usr/bin/env bash
# Cancel ALL pending Alpaca paper orders and submit a fresh basket.
# Use when something about the current basket is wrong (e.g. an earnings
# event was discovered after the orders were already queued) and you
# want to regenerate from scratch.
set -e

cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

if [ ! -f .env ]; then
    echo "ERROR: .env not found." >&2
    exit 1
fi

set -a
. ./.env
set +a

PYTHON="${PYTHON:-python3.13}"

echo "Step 1/3: cancelling all pending Alpaca paper orders..."
"$PYTHON" - <<'PY'
import os
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

client = TradingClient(
    os.environ["ALPACA_API_KEY"],
    os.environ["ALPACA_API_SECRET"],
    paper=True,
)
req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
orders = client.get_orders(req)
if not orders:
    print("  (no open orders)")
else:
    for o in orders:
        try:
            client.cancel_order_by_id(o.id)
            print(f"  cancelled {o.symbol} ({o.side}, id={o.id})")
        except Exception as exc:
            print(f"  FAILED to cancel {o.symbol}: {exc}")
PY

echo
echo "Step 2/3: refreshing earnings cache for full universe (this can take a few minutes)..."
# Drop the entire earnings cache so the new multi-source fetcher runs against
# every ticker (the original cache may have stale Nones from the first run).
rm -f data/earnings.json

echo
echo "Step 3/3: rebuilding the basket with the earnings filter active..."
"$PYTHON" -m paper run \
    --as-of "$(date +%Y-%m-%d)" \
    --broker alpaca \
    --fetch
