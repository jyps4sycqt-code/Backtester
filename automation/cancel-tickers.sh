#!/usr/bin/env bash
# Cancel any open orders for the specified tickers on Alpaca paper.
# Usage: bash automation/cancel-tickers.sh CAT COP MRK
set -e

cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

if [ "$#" -lt 1 ]; then
    echo "Usage: bash automation/cancel-tickers.sh TICKER [TICKER ...]" >&2
    exit 1
fi

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run automation/setup-credentials.sh first." >&2
    exit 1
fi

set -a
. ./.env
set +a

PYTHON="${PYTHON:-python3.13}"

exec "$PYTHON" - "$@" <<'PY'
import os
import sys

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import QueryOrderStatus
from alpaca.trading.requests import GetOrdersRequest

targets = {t.upper() for t in sys.argv[1:]}
client = TradingClient(
    os.environ["ALPACA_API_KEY"],
    os.environ["ALPACA_API_SECRET"],
    paper=True,
)

# Pull all open orders, filter to the requested symbols.
req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
orders = client.get_orders(req)
to_cancel = [o for o in orders if o.symbol.upper() in targets]

if not to_cancel:
    print(f"No open orders found for: {', '.join(sorted(targets))}")
    sys.exit(0)

print(f"Cancelling {len(to_cancel)} open order(s):")
for o in to_cancel:
    print(f"  {o.symbol:<6}  id={o.id}  side={o.side}  qty/notional={o.qty or o.notional}  status={o.status}")
    try:
        client.cancel_order_by_id(o.id)
        print(f"    -> cancelled")
    except Exception as exc:
        print(f"    -> FAILED: {exc}")

# Also liquidate any positions that were already filled in those tickers.
positions = {p.symbol.upper(): p for p in client.get_all_positions()}
for sym in targets:
    if sym in positions:
        print(f"Closing existing position in {sym} (qty={positions[sym].qty})")
        try:
            client.close_position(sym)
            print("  -> close submitted")
        except Exception as exc:
            print(f"  -> FAILED: {exc}")
PY
