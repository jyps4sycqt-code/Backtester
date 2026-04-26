#!/usr/bin/env bash
# Weekly paper-trading run. Invoked by the launchd job each Sunday.
# Logs everything to results/logs/automation_<timestamp>.log
set -e

cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

mkdir -p results/logs
TS="$(date +%Y-%m-%dT%H%M%S)"
LOG="results/logs/automation_${TS}.log"

# Tee everything from this point on into the log file.
exec > >(tee -a "$LOG") 2>&1

echo "[$TS] === weekly paper run starting ==="

if [ ! -f .env ]; then
    echo "ABORT: .env not found"
    exit 1
fi

set -a
. ./.env
set +a

if [ -z "${ALPACA_API_KEY:-}" ] || [ -z "${ALPACA_API_SECRET:-}" ]; then
    echo "ABORT: missing Alpaca credentials in .env"
    exit 1
fi

PYTHON="${PYTHON:-python3.13}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ABORT: $PYTHON not in PATH"
    exit 1
fi

# Stay current with any strategy/code changes pushed to the branch.
echo "[$TS] git fetch + ff-only pull"
git fetch --quiet origin || echo "(git fetch failed, continuing with local code)"
git pull --ff-only --quiet || echo "(git pull failed, continuing with local code)"

echo "[$TS] running paper rebalance"
"$PYTHON" -m paper run \
    --as-of "$(date +%Y-%m-%d)" \
    --broker alpaca \
    --fetch

echo "[$TS] === done ==="
