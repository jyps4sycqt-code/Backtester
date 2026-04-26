#!/usr/bin/env bash
# Convenience wrapper for the paper trader. Defaults to today's date and
# the dry-run broker. To use Alpaca, export ALPACA_API_KEY/ALPACA_API_SECRET
# and run: BROKER=alpaca bash run-paper.sh
set -e

PYTHON="${PYTHON:-python3.13}"
AS_OF="${AS_OF:-$(date +%Y-%m-%d)}"
BROKER="${BROKER:-auto}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON not found in PATH." >&2
    exit 1
fi

echo "Paper run: as-of $AS_OF, broker=$BROKER"
echo

exec "$PYTHON" -m paper run \
    --as-of "$AS_OF" \
    --broker "$BROKER" \
    --fetch
