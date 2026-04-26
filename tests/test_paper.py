"""Tests for the paper trader (DryRunBroker only -- no network)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from paper.dry_run import DryRunBroker
from paper.runner import PaperRunner
from trader.config import StrategyConfig


def test_paper_runner_produces_log(tmp_path: Path, cache, synth_universe, sectors):
    broker = DryRunBroker(log_path=tmp_path / "dry.jsonl", starting_cash=1_000.0)
    runner = PaperRunner(
        broker=broker,
        cache=cache,
        universe=synth_universe,
        config=StrategyConfig(picks=4, max_per_sector=1),
        sectors=sectors,
        log_dir=tmp_path,
    )
    run = runner.run(pd.Timestamp("2022-06-30"))
    assert run.log_path.exists()
    payload = json.loads(run.log_path.read_text())
    assert payload["broker"] == "dry-run"
    assert len(payload["picks"]) == 4
    assert any(entry["action"] == "buy" for entry in payload["rebalance"])


def test_paper_runner_dry_does_not_submit(tmp_path: Path, cache, synth_universe, sectors):
    broker = DryRunBroker(log_path=tmp_path / "dry.jsonl", starting_cash=1_000.0)
    runner = PaperRunner(
        broker=broker, cache=cache, universe=synth_universe,
        config=StrategyConfig(picks=4, max_per_sector=1),
        sectors=sectors, log_dir=tmp_path,
    )
    run = runner.run(pd.Timestamp("2022-06-30"), dry=True)
    # No actual submit calls means the broker's JSONL has no submit events.
    if (tmp_path / "dry.jsonl").exists():
        events = [json.loads(line) for line in (tmp_path / "dry.jsonl").read_text().splitlines() if line.strip()]
        assert all(e.get("event") != "submit" for e in events)
    assert any(action.get("action", "").startswith("would_") for action in run.rebalance_log)
