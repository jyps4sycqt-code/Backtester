#!/usr/bin/env bash
# Convenience wrapper so you can run the backtest without typing `--` flags
# (which macOS auto-corrects to en-dashes). Just: `bash run-backtest.sh`
set -e

PYTHON="${PYTHON:-python3.13}"
START="${START:-2018-01-01}"
END="${END:-2025-12-31}"
OUT="${OUT:-results}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON not found in PATH. Install Python 3.10+ or set PYTHON=..." >&2
    exit 1
fi

echo "Running backtest: $START -> $END (Python: $PYTHON)"
echo "First-time runs fetch ~7 years of OHLCV via yfinance and take a few minutes."
echo

exec "$PYTHON" -m backtest \
    --start "$START" \
    --end "$END" \
    --fetch \
    --output-dir "$OUT"
