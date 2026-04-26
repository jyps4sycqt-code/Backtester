# paper

Paper-trade the weekly basket strategy on a real cadence using the same `trader.pipeline.run_pipeline` that the backtest validates.

## Brokers

| Adapter         | When                                                              | Network |
|-----------------|-------------------------------------------------------------------|---------|
| `DryRunBroker`  | Default; logs intended trades to a JSONL file. Use to sanity-check the runner before connecting anything. | No |
| `AlpacaPaperBroker` | Set `ALPACA_API_KEY` + `ALPACA_API_SECRET`. Submits notional market orders to Alpaca's paper endpoint. Refuses any non-paper URL. | Yes |

Real-money execution is **intentionally not provided**. To go live, write a separate adapter and gate it behind an explicit confirmation.

## Usage

```bash
# One-shot rebalance using whichever broker is auto-selected (Alpaca if creds set,
# else dry-run). Selection date defaults to today UTC.
python -m paper run --as-of 2026-04-24

# Force dry-run, log intentions only without submitting:
python -m paper run --as-of 2026-04-24 --broker dry-run --dry

# Refresh price cache via yfinance before running (needs `pip install yfinance`):
python -m paper run --as-of 2026-04-24 --fetch

# Show broker cash + positions:
python -m paper status --broker alpaca
```

## Scheduling

The runner is one-shot — you schedule it externally. Two common setups:

**cron** (Sunday 18:00 UTC = early Sunday evening US):

```cron
0 18 * * SUN cd /path/to/trader && /path/to/python -m paper run --fetch >> logs/paper.log 2>&1
```

**GitHub Actions** (uses repository secrets for Alpaca creds):

```yaml
on:
  schedule:
    - cron: "0 18 * * SUN"
jobs:
  paper:
    runs-on: ubuntu-latest
    env:
      ALPACA_API_KEY: ${{ secrets.ALPACA_API_KEY }}
      ALPACA_API_SECRET: ${{ secrets.ALPACA_API_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt yfinance alpaca-py
      - run: python -m paper run --fetch --broker alpaca
```

## Outputs

For each run, `results/paper_<DATE>.json` records the selected picks, all rebalance actions taken (or "would_buy" / "would_liquidate" entries if `--dry`), and any pipeline warnings. The dry-run broker also writes `results/paper_dryrun.jsonl` with one JSON object per submitted/liquidated order.

## Workflow with the backtester

1. Run the backtester. Look at `summary.md` section D (random baseline). If the strategy doesn't clear that bar, **don't paper trade**.
2. With Alpaca paper credentials set, run `python -m paper run` weekly for at least 8–12 weeks.
3. Compare the live paper equity curve against the backtest's expected curve over the same window. They should be within reasonable bounds; large divergence means either the backtest is wrong or live conditions differ.
4. Only after that should you consider a real-money adapter.
