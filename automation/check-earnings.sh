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

# Hold window: today through 7 calendar days out covers Mon-open to
# next-Mon-open even with weekends.
today = pd.Timestamp.utcnow().normalize()
window_start = today
window_end = today + pd.Timedelta(days=7)

print(f"Tickers held: {', '.join(tickers)}")
print(f"Window:       {window_start.date()} to {window_end.date()}")
print()
print("Fetching next earnings dates via yfinance...")

earnings = ensure_earnings(tickers, "data/earnings.json", fetch=True)
in_window = tickers_reporting_in(earnings, window_start, window_end)

print()
print(f"{'Ticker':<8} {'Next earnings':<14} {'In hold window?'}")
print("-" * 40)
flagged = []
for t in tickers:
    iso = earnings.get(t.upper())
    in_w = "YES" if t.upper() in in_window else ""
    if t.upper() in in_window:
        flagged.append(t)
    print(f"{t:<8} {iso or 'unknown':<14} {in_w}")

print()
if flagged:
    print(f"WARNING: {len(flagged)} name(s) report earnings during the hold window:")
    for t in flagged:
        print(f"  - {t}: earnings {earnings[t.upper()]}")
    print()
    print("Consider liquidating these manually in Alpaca to avoid the gap risk.")
    print("From next Sunday's run onward, the strategy will exclude them automatically.")
else:
    print("No basket names report this hold window. Strategy is clean.")
PY
