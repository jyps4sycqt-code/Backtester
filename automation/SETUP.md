# Automation setup (Alpaca paper, macOS launchd)

Three steps. Each is one command. After step 3 the strategy runs every Sunday at 18:00 local time without you needing to touch it.

---

## 1. Set up Alpaca paper credentials

Create a free Alpaca account at https://alpaca.markets, then go to https://app.alpaca.markets/paper/dashboard/overview, click **View** under "Your API Keys" (right side), and copy the **Key ID** and **Secret Key**.

Then in the `Backtester` directory:

```
bash automation/setup-credentials.sh
```

It will prompt for the Key and Secret and write them to a `.env` file (gitignored, permissions 600 — keys never leave your machine).

---

## 2. First run — submit today's basket

```
bash automation/first-run.sh
```

This installs `alpaca-py`, builds today's snapshot from yfinance, runs the pipeline, and submits 5 equal-dollar buy orders to Alpaca paper. If today is the weekend or markets are closed, the orders queue and fill at the next open.

You'll see output like:

```
Paper run @ 2026-04-26 (tier=tier1_strict)
Cash after: $99,xxx.xx
Picks:
  XYZ    tier=1  sector=Technology      composite=+1.42  last=$123.45
  ...
Log: results/paper_2026-04-26.json
```

Check your basket on the Alpaca paper dashboard: https://app.alpaca.markets/paper/dashboard/overview — orders will appear in **Activities** and positions in **Positions** after the next market open.

---

## 3. Schedule it weekly

```
bash automation/install-launchd.sh
```

This installs a macOS LaunchAgent that runs `automation/run-weekly.sh` every Sunday at 18:00 local time. The job:

1. `git pull` to stay current with any strategy changes.
2. Refreshes the price cache via yfinance.
3. Calls the paper trader, which liquidates names that left the basket and buys new ones.
4. Logs everything to `results/logs/automation_<timestamp>.log`.

Verify it's installed:

```
launchctl list | grep com.trader
```

You should see `com.trader.weekly` in the output (a number, a status, then the label). Status `0` means last run succeeded; non-zero means a failure that's recorded in `results/logs/launchd.err.log`.

---

## Useful follow-up commands

Trigger a run manually any time:

```
bash automation/run-weekly.sh
```

Check current cash and positions on Alpaca paper:

```
python3.13 -m paper status --broker alpaca
```

View today's run log:

```
ls -t results/logs/ | head -3
cat results/logs/automation_<latest>.log
```

Remove the schedule:

```
bash automation/uninstall-launchd.sh
```

---

## What to expect

- **Drawdowns:** the backtest shows up to ~35% drawdown on $1k starting capital — about $650 at the worst point. Paper, so no real money at risk, but sit through it without intervening so you see how the live experience matches the backtest.
- **Cadence:** weekly rebalance. New picks every Sunday, fills Monday open, hold to next Monday.
- **Comparison:** every 4 weeks, compare your Alpaca paper P&L to the backtest's expected weekly returns. If they diverge by more than a couple of percent over a quarter, something is off — the live data feed differs from yfinance, or the strategy changed without a re-validation.

---

## Going to real money — DO NOT DO THIS YET

This repo's `paper.alpaca.AlpacaPaperBroker` refuses to talk to anything other than the paper endpoint. Real-money execution is intentionally absent. After 8–12 weeks of paper performance that matches backtest expectations, write a `LiveAlpacaBroker` that points at the live endpoint and gate it behind a confirmation prompt. **Do not skip that confirmation step.**
