# backtest

Replay the weekly basket strategy against historical data.

## Usage

```bash
python -m backtest \
  --start 2018-01-01 \
  --end 2025-12-31 \
  --capital 1000 \
  --slippage-bps 5 \
  --in-sample-split 2022-12-31 \
  --output-dir results \
  --fetch          # populate cache via yfinance the first time
```

## Mechanics

- **Selection** at every Friday close, using only data with timestamp ≤ that Friday.
- **Execution** at the next available trading-day open (Monday, or next session if Monday is a holiday). Orders are equal-dollar across `picks` (default 5), with **5 bps slippage per side** and zero commission.
- **Hold** exactly one week: enter Mon t open, exit Mon t+1 open.
- **Cash drag**: if the pipeline returns fewer than `picks` names, the unfilled portion sits in cash at 0%.

## Outputs

After a run, `results/` contains:

| File                | Contents                                                                  |
|---------------------|---------------------------------------------------------------------------|
| `summary.md`        | Config + caveats + sections A–E (see below).                              |
| `equity.csv`        | Weekly equity curve.                                                      |
| `equity_curve.png`  | Strategy vs. SPY / QQQ / RSP / random, with drawdown subplot.             |
| `trades.parquet`    | Every weekly fill: ticker, sector, tier, composite score, components, entry/exit, P&L. |

`summary.md` always contains:

- **A. Performance summary**: total return, CAGR, Sharpe, Sortino, max drawdown, time-to-recovery, weekly win rate, win-vs-loss week averages, and an in-sample vs. out-of-sample table. Plus best 10 / worst 10 weeks with the picks that drove them.
- **B. Tier attribution**: average return / hit rate / count per tier (1–5). Flags tier 4–5 if they underperform.
- **C. Sector attribution**: gross P&L and % per sector. Flags single-sector concentration over 50%.
- **D. Random-baseline comparison** (the most important metric). Re-runs the simulator with composite scoring replaced by random selection from the same gated pool and same diversification. If the strategy doesn't beat the baseline by Sharpe diff > 0.3, the report flags it as **FAIL — composite may be noise**.
- **E. Equity curve plot**.

## How to interpret the output

- **Sharpe diff vs. random < 0.3** → the composite is doing nothing. Don't paper-trade it.
- **All P&L from one sector** → you're probably riding a single industry trend, not picking stocks.
- **OOS performance much worse than IS** → the strategy is fit to its training window. Reject and rebuild.
- **Tier 4/5 picks have negative average return** → the relaxation logic is hurting; cap the basket at fewer picks rather than relaxing.

## Customizing the universe

Pass `--universe path/to/tickers.txt` (one per line, `#` for comments). Without it, the run uses a static current S&P 500 ∪ Nasdaq 100 union and emits a survivorship warning at the top of the report.
