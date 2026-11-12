"""Command line interface for AutoCetacean."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from autocetacean import __version__
from autocetacean.ledger import PersistentLedger
from autocetacean.replay import ReplayEngine, ReplayError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="autocetacean",
        description="Deterministic runtime and state-machine ledger for autonomous agents.",
    )
    parser.add_argument("--version", action="version", version=f"autocetacean {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # ledger command
    ledger_p = subparsers.add_parser("ledger", help="Inspect or verify persistent memory ledger")
    ledger_p.add_argument("path", help="Path to ledger JSON file")
    ledger_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    # replay command
    replay_p = subparsers.add_parser("replay", help="Replay and visualize an execution trace")
    replay_p.add_argument("trace_file", help="Path to a JSON or JSONL execution trace")
    replay_p.add_argument("--json", action="store_true", help="Output the replay summary as JSON")
    replay_p.add_argument("--plain", action="store_true", help="Disable ANSI colors in terminal output")
    replay_p.add_argument("--html", metavar="PATH", help="Export a standalone HTML visualization")

    args = parser.parse_args(argv)

    if args.command == "ledger":
        p = Path(args.path)
        if not p.exists():
            print(f"autocetacean: ledger file not found: {args.path}", file=sys.stderr)
            return 2
        ledger = PersistentLedger(storage_path=p)
        snap = ledger.export_snapshot()
        if args.json:
            print(json.dumps(snap, indent=2, ensure_ascii=False))
        else:
            print(f"AutoCetacean Ledger Revision {snap['revision']}")
            print(f"Usage: {snap['total_bytes']} / {snap['max_bytes']} bytes")
            print(f"Slots: {list(snap['slots'].keys())}")
        return 0

    if args.command == "replay":
        p = Path(args.trace_file)
        if not p.exists():
            print(f"autocetacean: trace file not found: {args.trace_file}", file=sys.stderr)
            return 2
        try:
            replay = ReplayEngine(p)
            if args.html:
                replay.export_html(args.html)
            if args.json:
                print(json.dumps(replay.export_summary(), indent=2, ensure_ascii=False))
            else:
                print(replay.render_terminal("plain" if args.plain else "ansi"))
            return 0
        except (ReplayError, OSError, ValueError) as exc:
            print(f"autocetacean: invalid execution trace: {exc}", file=sys.stderr)
            return 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
