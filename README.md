# trader

Weekly stock-basket rotation strategy with three coordinated pieces:

| Package    | Purpose                                                                                    |
|------------|--------------------------------------------------------------------------------------------|
| `trader/`  | The strategy as **pure functions** — universe, macro read, scoring, kill list, diversify, `run_pipeline(snapshot, config) → picks`. Single source of truth. |
| `backtest/`| Replays the pipeline against historical data to validate it has positive expected value before risking capital. |
| `paper/`   | Runs the same pipeline on a weekly cadence and submits to a paper broker (DryRun by default; Alpaca paper supported). |

The backtest and paper trader **import the same `run_pipeline` function**. If they diverge, the backtest is worthless — so all selection logic lives in `trader/` and is shared.

For a visual walkthrough of the algorithm and the weekly cadence, see [`docs/algorithm.md`](docs/algorithm.md).

---

## Workflow

You should run these in order before risking real money.

1. **Backtest** — does the strategy beat random selection from the same gated pool, and beat SPY/QQQ/RSP?
2. **Paper trade** — does it work in real-world cadence, with realistic data, broker, and timing?
3. **Real money** — only after the first two pass. Real-money execution is **not** wired up in this repo by design; you implement it yourself, gated behind an explicit confirmation.

---

## Install

```bash
pip install -r requirements.txt
# optional, for live data and paper trading:
pip install yfinance alpaca-py
```

## Quick start

```bash
# 1) Pull data and run a backtest
python -m backtest --start 2018-01-01 --end 2025-12-31 --fetch
# -> results/summary.md, results/equity_curve.png, results/trades.parquet

# 2) Paper trade once (dry run, no broker required)
python -m paper run --as-of 2026-04-24 --fetch

# 3) Paper trade against Alpaca (requires credentials)
export ALPACA_API_KEY=... ALPACA_API_SECRET=...
python -m paper run --as-of 2026-04-24 --broker alpaca
```

## Repository layout

```
trader/             # Pure pipeline (imported by backtest and paper)
  config.py
  universe.py
  data.py           # Cached parquet OHLCV
  macro.py
  scoring.py
  kill_list.py
  diversify.py
  candidates.py     # Tiered relaxation
  pipeline.py       # run_pipeline(snapshot, config) -> PipelineResult

backtest/           # Historical replay
  simulator.py      # Friday-select, Monday-execute weekly loop
  metrics.py        # Sharpe, drawdown, etc.
  baseline.py       # Random-selection comparator
  report.py         # summary.md + equity_curve.png + trades.parquet
  cli.py            # `python -m backtest`

paper/              # Live cadence
  broker.py         # Broker protocol
  dry_run.py        # JSONL-only; no network
  alpaca.py         # Alpaca paper API adapter
  runner.py         # Weekly rebalance
  cli.py            # `python -m paper run / status`

tests/              # Offline, synthetic-data tests (no network)
```

## Caveats (read these)

- **Survivorship bias.** Default universe is current S&P 500 ∪ Nasdaq 100. Stocks delisted, acquired, or ejected from the index are absent, biasing returns upward. Pass `--universe path/to/tickers.txt` with point-in-time membership to fix.
- **No fundamentals in v1.** yfinance returns current-only fundamentals (P/E, EPS, sector). Using them in a backtest would inject look-ahead bias, so v1 disables fundamentals entirely. The composite uses momentum, trend, low-vol, and short reversal only.
- **No live news feed.** The kill list supports keyword scanning of headlines (`apply_kill_list(headlines=...)`), but no feed is wired up. v1 uses an explicit ticker exclusion set.
- **Restatement bias** is not modeled — acceptable at a weekly horizon.
- **Sectors** are not auto-discovered. Pass them through `SimulatorConfig.sectors` / `PaperRunner.sectors`. Without them all picks land in `"Unknown"` and sector diversification has no effect.
- **Real-money trading is intentionally absent.** `paper.alpaca.AlpacaPaperBroker` refuses any base URL that isn't the paper endpoint.

## Running tests

```bash
python -m pytest
```

The suite runs offline using deterministic synthetic price data. Includes a no-look-ahead invariant.

## Developing

Each public stage in `trader/` is a pure function. The pipeline calls them in order:

```
universe -> kill list -> tiered candidates -> composite score -> sector diversify -> 5 picks
```

When you change selection logic, change it **only in `trader/`**. Both backtest and paper inherit the change automatically.
