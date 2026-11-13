"""Command line interface for AutoCetacean."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from autocetacean import __version__
from autocetacean.graph import StateGraph
from autocetacean.ledger import PersistentLedger
from autocetacean.replay import ReplayEngine, ReplayError
from autocetacean.visualizer import GraphVisualizer


def _load_graph_target(target: str) -> StateGraph:
    """Load ``module:attribute`` or ``path.py:attribute`` as a StateGraph."""
    if not target or ":" not in target:
        raise ValueError("target must use module_path:graph_var or file.py:graph_var")

    module_ref, attribute = target.rsplit(":", 1)
    if not module_ref or not attribute or not attribute.isidentifier():
        raise ValueError("target must use module_path:graph_var or file.py:graph_var")

    module: ModuleType
    path = Path(module_ref).expanduser()
    if path.exists() or path.suffix == ".py":
        if not path.exists():
            raise FileNotFoundError(f"graph file not found: {path}")
        if not path.is_file():
            raise ValueError(f"graph target is not a file: {path}")
        module_name = f"autocetacean_graph_target_{abs(hash(path.resolve()))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"unable to load graph file: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    else:
        try:
            module = importlib.import_module(module_ref)
        except ModuleNotFoundError as exc:
            module_path = Path(*module_ref.split("."))
            candidates = (module_path.with_suffix(".py"), Path.cwd() / module_path.with_suffix(".py"))
            source_path = next((candidate for candidate in candidates if candidate.is_file()), None)
            if source_path is None:
                raise ImportError(f"module not found: {module_ref}") from exc
            module_name = f"autocetacean_graph_target_{abs(hash(source_path.resolve()))}"
            spec = importlib.util.spec_from_file_location(module_name, source_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"unable to load graph module: {module_ref}") from exc
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception as exc:
            raise ImportError(f"unable to import module {module_ref!r}: {exc}") from exc

    if not hasattr(module, attribute):
        raise AttributeError(f"graph attribute not found: {module_ref}:{attribute}")
    graph = getattr(module, attribute)
    if not isinstance(graph, StateGraph):
        raise TypeError(f"target {target!r} is {type(graph).__name__}, expected StateGraph")
    return graph


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

    # graph command
    graph_p = subparsers.add_parser("graph", help="Export a StateGraph topology")
    graph_p.add_argument("target", help="Graph object as module_path:graph_var or file.py:graph_var")
    graph_p.add_argument("--format", choices=("mermaid", "html"), default="mermaid", help="Export format")
    graph_p.add_argument("--output", metavar="PATH", help="Write the export to a file")
    graph_p.add_argument("--title", default="AutoCetacean Workflow", help="HTML document title")

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

    if args.command == "graph":
        try:
            graph = _load_graph_target(args.target)
            mermaid = GraphVisualizer.to_mermaid(graph)
            if args.output:
                document = GraphVisualizer.to_html(graph, args.title) if args.format == "html" else mermaid
                Path(args.output).write_text(document, encoding="utf-8")
            else:
                # Terminal output stays copy/paste-friendly Mermaid source.
                print(mermaid, end="")
            return 0
        except (AttributeError, FileNotFoundError, ImportError, OSError, TypeError, ValueError) as exc:
            print(f"autocetacean: unable to export graph: {exc}", file=sys.stderr)
            return 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
