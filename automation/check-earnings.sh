#!/usr/bin/env bash
# Check the most recent paper basket for upcoming earnings during the
# holding window (Mon open -> next Mon open). Prints any names whose
# next earnings date falls inside that window so you can decide whether
# to manually liquidate.
set -e

cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

PYTHON="${PYTHON:-python3.13}"

LATEST=$(ls -t results/paper_*.json 2>/dev/null | head -1)
if [ -z "$LATEST" ]; then
    echo "ERROR: no paper run logs found in results/. Run automation/first-run.sh first." >&2
    exit 1
fi

echo "Checking earnings for basket in: $LATEST"
echo

exec "$PYTHON" - "$LATEST" <<'PY'
import json
import sys
from pathlib import Path

import pandas as pd

from trader.earnings import ensure_earnings, tickers_reporting_in

log = json.loads(Path(sys.argv[1]).read_text())
tickers = [p["ticker"] for p in log.get("picks", [])]
if not tickers:
    print("Basket is empty -- nothing to check.")
    sys.exit(0)

today = pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)
window_start = today
window_end = today + pd.Timedelta(days=7)

print(f"Tickers held: {', '.join(tickers)}")
print(f"Window:       {window_start.date()} to {window_end.date()}")
print()
print("Fetching next earnings dates via yfinance (tries 3 sources)...")

# Force-refresh: drop any cached entries for the held tickers so the new
# multi-source fetcher runs against them, even if a stale None was cached.
cache_path = Path("data/earnings.json")
if cache_path.exists():
    cache = json.loads(cache_path.read_text())
    held_upper = {t.upper() for t in tickers}
    cache = {k: v for k, v in cache.items() if k.upper() not in held_upper}
    cache_path.write_text(json.dumps(cache, indent=2))

earnings = ensure_earnings(tickers, cache_path, fetch=True)
in_window = tickers_reporting_in(earnings, window_start, window_end)

print()
print(f"{'Ticker':<8} {'Next earnings':<14} {'In hold window?'}")
print("-" * 42)
flagged = []
unknown = []
for t in tickers:
    iso = earnings.get(t.upper())
    if iso is None:
        unknown.append(t)
        in_w = "?"
    elif t.upper() in in_window:
        flagged.append(t)
        in_w = "YES"
    else:
        in_w = "no"
    print(f"{t:<8} {iso or 'UNKNOWN':<14} {in_w}")

print()
if flagged:
    print(f"WARNING: {len(flagged)} name(s) report earnings during the hold window:")
    for t in flagged:
        print(f"  - {t}: earnings {earnings[t.upper()]}")
    print()
    print("Consider liquidating these manually in Alpaca to avoid the gap risk.")
    print("From next Sunday's run onward, the strategy excludes them automatically.")
elif unknown:
    print(f"INCONCLUSIVE: yfinance returned no earnings data for {len(unknown)} of {len(tickers)} names:")
    for t in unknown:
        print(f"  - {t}")
    print()
    print("This is a known yfinance reliability issue, not a guarantee they don't report.")
    print("Cross-check manually at https://finance.yahoo.com/calendar/earnings or")
    print("https://www.nasdaq.com/market-activity/earnings -- search each ticker.")
else:
    print(f"VERIFIED CLEAN: all {len(tickers)} names have known earnings dates outside the window.")
PY
