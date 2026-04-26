#!/usr/bin/env bash
# Run the paper trader once for today, against Alpaca paper.
# Use BEFORE installing the launchd schedule, to verify everything works.
set -e

cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Run automation/setup-credentials.sh first." >&2
    exit 1
fi

set -a
. ./.env
set +a

if [ -z "${ALPACA_API_KEY:-}" ] || [ -z "${ALPACA_API_SECRET:-}" ]; then
    echo "ERROR: ALPACA_API_KEY / ALPACA_API_SECRET missing in .env." >&2
    exit 1
fi

PYTHON="${PYTHON:-python3.13}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON not found in PATH." >&2
    exit 1
fi

echo "Ensuring alpaca-py is installed..."
"$PYTHON" -m pip install --quiet alpaca-py >/dev/null

echo
echo "Submitting today's basket to Alpaca paper..."
exec "$PYTHON" -m paper run \
    --as-of "$(date +%Y-%m-%d)" \
    --broker alpaca \
    --fetch
