"""Markdown summary + plot generation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from backtest.metrics import PerformanceStats, benchmark_stats, compute_stats
from backtest.simulator import SimulationOutput


def _fmt_pct(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x * 100:.2f}%"


def _fmt_ratio(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "n/a"
    return f"{x:.2f}"


def _to_md_table(df: pd.DataFrame, *, index: bool = True) -> str:
    """Render a DataFrame as a markdown table without requiring tabulate."""
    if df.empty:
        return "n/a"
    try:
        return df.to_markdown(index=index)
    except ImportError:
        pass
    df_show = df.reset_index() if index else df.copy()
    cols = list(df_show.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    rows = []
    for _, row in df_show.iterrows():
        cells = []
        for v in row.tolist():
            if isinstance(v, float):
                cells.append(f"{v:.4f}")
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep, *rows])


def _stats_row(name: str, s: PerformanceStats) -> str:
    return (
        f"| {name} "
        f"| {_fmt_pct(s.total_return)} "
        f"| {_fmt_pct(s.cagr)} "
        f"| {_fmt_pct(s.annualized_volatility)} "
        f"| {_fmt_ratio(s.sharpe_ratio)} "
        f"| {_fmt_ratio(s.sortino_ratio)} "
        f"| {_fmt_pct(s.max_drawdown)} "
        f"| {s.max_drawdown_weeks} "
        f"| {s.time_to_recovery_weeks if s.time_to_recovery_weeks is not None else 'n/a'} "
        f"| {_fmt_pct(s.weekly_win_rate)} "
        f"|"
    )


@dataclass
class Report:
    path: Path
    plot_path: Optional[Path]


def _weekly_baseline_returns(equity: pd.Series, baseline_equity: pd.Series) -> tuple[float, float, float, float]:
    """(strat_avg_win, strat_avg_loss, beat_baseline_rate)"""
    if baseline_equity.empty:
        return (np.nan, np.nan, np.nan, np.nan)
    strat = equity.pct_change().dropna()
    base = baseline_equity.reindex(equity.index, method="ffill").pct_change().dropna()
    aligned = pd.concat([strat, base], axis=1, join="inner")
    aligned.columns = ["strat", "base"]
    if aligned.empty:
        return (np.nan, np.nan, np.nan, np.nan)
    wins = aligned.loc[aligned["strat"] > 0, "strat"]
    losses = aligned.loc[aligned["strat"] < 0, "strat"]
    beat_rate = float((aligned["strat"] > aligned["base"]).mean())
    return (
        float(wins.mean()) if not wins.empty else np.nan,
        float(losses.mean()) if not losses.empty else np.nan,
        beat_rate,
        float(aligned["strat"].mean() - aligned["base"].mean()),
    )


def write_report(
    *,
    output_dir: Path,
    config_summary: dict,
    sim: SimulationOutput,
    baseline_sim: Optional[SimulationOutput],
    benchmarks: dict[str, pd.Series],
    in_sample_split: Optional[pd.Timestamp],
    warnings: Sequence[str],
    git_sha: Optional[str],
) -> Report:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    eq = sim.equity
    stats = compute_stats(eq)

    weekly_index = eq.index
    bench_stats = {name: benchmark_stats(series, weekly_index) for name, series in benchmarks.items()}

    base_stats = compute_stats(baseline_sim.equity) if baseline_sim is not None else None

    # In/out of sample
    is_stats = oos_stats = None
    if in_sample_split is not None:
        is_eq = eq.loc[eq.index <= in_sample_split]
        oos_eq = eq.loc[eq.index > in_sample_split]
        is_stats = compute_stats(is_eq) if len(is_eq) > 1 else None
        oos_stats = compute_stats(oos_eq) if len(oos_eq) > 1 else None

    spy = benchmarks.get("SPY", pd.Series(dtype=float))
    aw, al, beat_rate, edge = _weekly_baseline_returns(eq, spy)

    # Tier attribution
    trades = sim.trades
    tier_table = pd.DataFrame()
    if not trades.empty and "tier" in trades.columns:
        trades = trades.copy()
        trades["pct_return"] = (trades["exit_price"] / trades["entry_price"] - 1.0)
        tier_table = trades.groupby("tier").agg(
            n_picks=("ticker", "count"),
            avg_return=("pct_return", "mean"),
            hit_rate=("pct_return", lambda s: (s > 0).mean()),
            total_pnl=("position_pnl", "sum"),
        ).round(4)

    sector_table = pd.DataFrame()
    if not trades.empty and "sector" in trades.columns:
        sector_table = trades.groupby("sector").agg(
            n_picks=("ticker", "count"),
            total_pnl=("position_pnl", "sum"),
        ).sort_values("total_pnl", ascending=False).round(2)
        total_pnl = sector_table["total_pnl"].sum()
        if total_pnl != 0:
            sector_table["pct_of_pnl"] = (sector_table["total_pnl"] / total_pnl * 100).round(1)

    # Best / worst weeks
    best_weeks_md = "n/a"
    worst_weeks_md = "n/a"
    if sim.baskets:
        weekly_df = pd.DataFrame([
            {"exit_date": b.exit_date, "weekly_return": b.weekly_return,
             "tickers": ",".join(b.pipeline_result.tickers())}
            for b in sim.baskets
        ])
        if not weekly_df.empty:
            best_weeks_md = weekly_df.nlargest(min(10, len(weekly_df)), "weekly_return").pipe(lambda d: _to_md_table(d, index=False))
            worst_weeks_md = weekly_df.nsmallest(min(10, len(weekly_df)), "weekly_return").pipe(lambda d: _to_md_table(d, index=False))

    plot_path = _maybe_plot(output_dir, sim, baseline_sim, benchmarks)

    md_lines: list[str] = []
    md_lines.append("# Backtest Summary\n")
    md_lines.append("## Configuration\n")
    md_lines.append("```")
    for k, v in config_summary.items():
        md_lines.append(f"{k}: {v}")
    md_lines.append(f"git_sha: {git_sha or 'unknown'}")
    md_lines.append("```\n")

    if warnings:
        md_lines.append("## Caveats\n")
        for w in warnings:
            md_lines.append(f"- {w}")
        md_lines.append("")

    md_lines.append("## A. Performance Summary\n")
    header = (
        "| Strategy | Total | CAGR | Vol | Sharpe | Sortino | MaxDD | DD wks | TTR wks | Win rate |\n"
        "|---|---|---|---|---|---|---|---|---|---|"
    )
    md_lines.append(header)
    md_lines.append(_stats_row("Strategy", stats))
    for name, bs in bench_stats.items():
        md_lines.append(_stats_row(name, bs))
    if base_stats is not None:
        md_lines.append(_stats_row("Random baseline", base_stats))
    md_lines.append("")

    if not np.isnan(beat_rate):
        md_lines.append(f"- Weekly win rate vs SPY: **{_fmt_pct(beat_rate)}**")
        md_lines.append(f"- Avg winning week: **{_fmt_pct(aw)}**, avg losing week: **{_fmt_pct(al)}**")
        md_lines.append(f"- Mean weekly edge over SPY: **{_fmt_pct(edge)}**\n")

    if is_stats is not None and oos_stats is not None:
        md_lines.append("### In-sample vs Out-of-sample\n")
        md_lines.append(header)
        md_lines.append(_stats_row(f"In-sample (≤ {in_sample_split.date()})", is_stats))
        md_lines.append(_stats_row(f"Out-of-sample (> {in_sample_split.date()})", oos_stats))
        md_lines.append("")

    md_lines.append("### Best 10 weeks\n")
    md_lines.append(best_weeks_md)
    md_lines.append("\n### Worst 10 weeks\n")
    md_lines.append(worst_weeks_md)
    md_lines.append("")

    md_lines.append("## B. Tier attribution\n")
    md_lines.append(_to_md_table(tier_table) if not tier_table.empty else "n/a")
    if not tier_table.empty and (tier_table["avg_return"].iloc[-1] < 0 if 5 in tier_table.index else False):
        md_lines.append("\n**Flag:** Tier 4–5 picks have negative average return -- relaxation logic may be hurting performance.\n")
    md_lines.append("")

    md_lines.append("## C. Sector attribution\n")
    md_lines.append(_to_md_table(sector_table) if not sector_table.empty else "n/a")
    if not sector_table.empty and "pct_of_pnl" in sector_table:
        top = sector_table["pct_of_pnl"].max()
        if top > 50:
            md_lines.append(f"\n**Flag:** {top:.0f}% of P&L from a single sector -- concentration risk.\n")
    md_lines.append("")

    md_lines.append("## D. Random-baseline comparison (CRITICAL)\n")
    if base_stats is not None:
        sharpe_diff = stats.sharpe_ratio - base_stats.sharpe_ratio
        md_lines.append(
            f"- Strategy Sharpe: **{_fmt_ratio(stats.sharpe_ratio)}**, "
            f"baseline Sharpe: **{_fmt_ratio(base_stats.sharpe_ratio)}**, "
            f"diff: **{sharpe_diff:+.2f}**"
        )
        verdict = "PASS" if sharpe_diff > 0.3 else "FAIL — composite may be noise"
        md_lines.append(f"- Verdict: **{verdict}** (>0.3 Sharpe edge needed)")
    else:
        md_lines.append("Random baseline not run.")
    md_lines.append("")

    md_lines.append("## E. Equity curve\n")
    if plot_path is not None:
        md_lines.append(f"![equity curve]({plot_path.name})")
    else:
        md_lines.append("Plot disabled (matplotlib unavailable).")
    md_lines.append("")

    out_path = output_dir / "summary.md"
    out_path.write_text("\n".join(md_lines))

    # Persist trades
    if not trades.empty:
        try:
            trades.to_parquet(output_dir / "trades.parquet")
        except Exception:
            trades.to_csv(output_dir / "trades.csv", index=False)

    eq.to_csv(output_dir / "equity.csv", index_label="date")

    return Report(path=out_path, plot_path=plot_path)


def _maybe_plot(
    output_dir: Path,
    sim: SimulationOutput,
    baseline_sim: Optional[SimulationOutput],
    benchmarks: dict[str, pd.Series],
) -> Optional[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})

    eq = sim.equity / sim.equity.iloc[0]
    ax1.plot(eq.index, eq.values, label="Strategy", linewidth=2)
    if baseline_sim is not None:
        b = baseline_sim.equity / baseline_sim.equity.iloc[0]
        ax1.plot(b.index, b.values, label="Random baseline", linestyle="--")
    for name, series in benchmarks.items():
        s = series.reindex(eq.index, method="ffill").dropna()
        if s.empty:
            continue
        ax1.plot(s.index, s / s.iloc[0], label=name, alpha=0.7)
    ax1.set_yscale("log")
    ax1.set_ylabel("Equity (log)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    dd = eq / eq.cummax() - 1.0
    ax2.fill_between(dd.index, dd.values, 0, color="tab:red", alpha=0.4)
    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    out = output_dir / "equity_curve.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out
