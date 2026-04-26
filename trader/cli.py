"""Top-level `trader` CLI: dispatches to backtest or paper subcommands."""
from __future__ import annotations

import sys


USAGE = """\
usage: trader <command> [args...]

commands:
  backtest   Run a historical replay (see `backtest --help`).
  paper      Run the paper trader (see `paper --help`).
"""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    cmd, rest = argv[0], argv[1:]
    if cmd == "backtest":
        from backtest.cli import main as backtest_main
        return backtest_main(rest)
    if cmd == "paper":
        from paper.cli import main as paper_main
        return paper_main(rest)
    print(USAGE, file=sys.stderr)
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
