"""Command line interface for AutoCetacean."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Tuple

from autocetacean import __version__
from autocetacean.graph import GraphExecutionError, StateGraph
from autocetacean.layers import LayerExecutionError
from autocetacean.ledger import PersistentLedger
from autocetacean.demo import run_demo
from autocetacean.mcp_proxy import MCPStdioRecorder, MCPStdioReplayer
from autocetacean.workspace import SubprocessToolGuard, WorkspaceGuardError
from autocetacean.replay import ReplayEngine, ReplayError
from autocetacean.types import ExecutionContext
from autocetacean.visualizer import GraphVisualizer


def _load_module_ref(module_ref: str) -> ModuleType:
    """Import a Python module by dotted name or filesystem path."""
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
        return module

    try:
        return importlib.import_module(module_ref)
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
        return module
    except Exception as exc:
        raise ImportError(f"unable to import module {module_ref!r}: {exc}") from exc


def _load_graph_target(target: str) -> StateGraph:
    """Load ``module:attribute`` or ``path.py:attribute`` as a StateGraph."""
    if not target or ":" not in target:
        raise ValueError("target must use module_path:graph_var or file.py:graph_var")

    module_ref, attribute = target.rsplit(":", 1)
    if not module_ref or not attribute or not attribute.isidentifier():
        raise ValueError("target must use module_path:graph_var or file.py:graph_var")

    module = _load_module_ref(module_ref)
    if not hasattr(module, attribute):
        raise AttributeError(f"graph attribute not found: {module_ref}:{attribute}")
    graph = getattr(module, attribute)
    if not isinstance(graph, StateGraph):
        raise TypeError(f"target {target!r} is {type(graph).__name__}, expected StateGraph")
    return graph


def _load_run_target(target: str) -> Tuple[str, Any]:
    """Load a StateGraph, zero-arg factory, or ``(ctx)`` runner callable."""
    if not target:
        raise ValueError("target must not be empty")

    if ":" in target:
        module_ref, attribute = target.rsplit(":", 1)
        if not module_ref or not attribute or not attribute.isidentifier():
            raise ValueError("target must use module_path:attr or file.py:attr")
        module = _load_module_ref(module_ref)
        if not hasattr(module, attribute):
            raise AttributeError(f"run target attribute not found: {module_ref}:{attribute}")
        obj = getattr(module, attribute)
    else:
        module = _load_module_ref(target)
        for fallback in ("build_graph", "graph"):
            if hasattr(module, fallback):
                obj = getattr(module, fallback)
                break
        else:
            raise AttributeError(f"run target {target!r} has neither 'build_graph' nor 'graph'")

    if isinstance(obj, StateGraph):
        return ("graph", obj)

    if callable(obj):
        sig = inspect.signature(obj)
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        required_pos = [p for p in positional if p.default is inspect.Parameter.empty]
        if len(required_pos) == 0:
            built = obj()
            if isinstance(built, StateGraph):
                return ("graph", built)
            raise TypeError(f"factory {target!r} returned {type(built).__name__}, expected StateGraph")
        if len(required_pos) == 1:
            return ("callable_ctx", obj)
        raise TypeError(f"callable {target!r} must accept 0 or 1 positional arguments")

    raise TypeError(f"target {target!r} is {type(obj).__name__}, expected StateGraph or callable")


def _parse_input_state(raw_input: str | None) -> dict[str, Any]:
    """Parse --input JSON string or @file.json into a state dictionary."""
    if raw_input is None:
        return {}
    if raw_input.startswith("@"):
        input_path = Path(raw_input[1:]).expanduser()
        if not input_path.is_file():
            raise FileNotFoundError(f"input JSON file not found: {input_path}")
        raw_text = input_path.read_text(encoding="utf-8")
    else:
        raw_text = raw_input
    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("input state must be a JSON object")
    return data


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
    graph_p.add_argument("--trace", metavar="PATH", help="Overlay an execution trace (JSON/JSONL) onto the graph")

    # run command
    run_p = subparsers.add_parser("run", help="Execute a StateGraph workflow")
    run_p.add_argument("target", help="Target as module_path:attr, file.py:attr, or module/file with build_graph/graph")
    run_p.add_argument("--input", dest="input_data", help="Initial state as JSON string or @file.json")
    run_p.add_argument("--trace-out", metavar="PATH", help="Export execution trace to a JSONL file")
    run_p.add_argument("--checkpoint-dir", metavar="DIR", help="Directory to persist rolling checkpoints")
    run_p.add_argument("--approve-gates", action="store_true", help="Automatically approve and resume Gate nodes")
    run_p.add_argument("--json", action="store_true", help="Output machine-readable JSON result")

    demo_p = subparsers.add_parser("demo", help="Run a self-contained demo of the guard and MCP replay")
    demo_p.add_argument("--json", action="store_true", help="Output the demo report as JSON")

    guard_p = subparsers.add_parser("guard", help="Run a command in a transactional workspace with gate verification")
    guard_p.add_argument("--workspace", required=True, help="Workspace directory to snapshot and protect")
    guard_p.add_argument("--cmd", required=True, help="Command to execute inside workspace")
    guard_p.add_argument("--gate", help="Deterministic verification command")
    guard_p.add_argument("--timeout", type=float, default=30.0, help="Command timeout seconds")
    guard_p.add_argument("--gate-timeout", type=float, default=60.0, help="Gate timeout seconds")
    guard_p.add_argument("--trace-out", metavar="PATH", help="Write JSON GuardOutcome trace to path")
    guard_p.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    rec_p = subparsers.add_parser("mcp-record", help="Proxy and record an MCP stdio JSON-RPC server session")
    rec_p.add_argument("--trace", required=True, help="Output JSONL trace file")
    rec_p.add_argument("--cwd", help="Working directory for MCP server")
    rec_p.add_argument("server_cmd", nargs=argparse.REMAINDER, help="Server command after '--'")

    rep_p = subparsers.add_parser("mcp-replay", help="Serve an offline deterministic MCP stdio replay from a trace")
    rep_p.add_argument("--trace", required=True, help="Input JSONL trace file")
    rep_p.add_argument("--strict", action="store_true", help="Fail with exit 1 if any call mismatches the trace")

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
            trace_obj = None
            if args.trace:
                trace_path = Path(args.trace)
                if not trace_path.exists():
                    print(f"autocetacean: trace file not found: {args.trace}", file=sys.stderr)
                    return 2
                trace_obj = ReplayEngine(trace_path)
            mermaid = GraphVisualizer.to_mermaid(graph, trace=trace_obj)
            if args.output:
                document = (
                    GraphVisualizer.to_html(graph, args.title, trace=trace_obj)
                    if args.format == "html"
                    else mermaid
                )
                Path(args.output).write_text(document, encoding="utf-8")
            else:
                # Terminal output stays copy/paste-friendly Mermaid source.
                print(mermaid, end="")
            return 0
        except (AttributeError, FileNotFoundError, ImportError, OSError, ReplayError, TypeError, ValueError) as exc:
            print(f"autocetacean: unable to export graph: {exc}", file=sys.stderr)
            return 2

    if args.command == "run":
        try:
            initial_state = _parse_input_state(args.input_data)
        except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"autocetacean: invalid --input: {exc}", file=sys.stderr)
            return 2

        try:
            kind, target_obj = _load_run_target(args.target)
        except (AttributeError, FileNotFoundError, ImportError, OSError, TypeError, ValueError) as exc:
            print(f"autocetacean: unable to load run target: {exc}", file=sys.stderr)
            return 2

        ctx = ExecutionContext(session_id="cli_run", state=initial_state)
        graph: StateGraph | None = None
        run_error: str | None = None

        try:
            if kind == "graph":
                graph = target_obj
                if args.checkpoint_dir:
                    graph.checkpoints.storage_dir = Path(args.checkpoint_dir)
                graph.run(ctx)
            else:
                res = target_obj(ctx)
                if isinstance(res, StateGraph):
                    graph = res
                    if args.checkpoint_dir:
                        graph.checkpoints.storage_dir = Path(args.checkpoint_dir)
                    graph.run(ctx)
                elif isinstance(res, ExecutionContext):
                    ctx = res
                elif res is not None:
                    raise TypeError(
                        f"run callable returned {type(res).__name__}, expected StateGraph, ExecutionContext, or None"
                    )

            if graph is not None and args.approve_gates:
                resume_guard = 0
                while ctx.variables.get("_suspended_at") and not ctx.is_halted:
                    resume_guard += 1
                    if resume_guard > ctx.max_steps:
                        ctx.is_halted = True
                        ctx.halt_reason = f"Gate resume limit exceeded ({ctx.max_steps})"
                        break
                    graph.resume(ctx, approved=True)
        except (GraphExecutionError, LayerExecutionError, TypeError, ValueError) as exc:
            run_error = str(exc)
        except Exception as exc:
            run_error = str(exc)

        if args.trace_out:
            try:
                ctx.export_trace(args.trace_out, format="jsonl")
            except OSError as exc:
                print(f"autocetacean: unable to write trace: {exc}", file=sys.stderr)
                return 2

        latest_cp = graph.checkpoints.get_latest() if graph is not None else None
        suspended_at = ctx.variables.get("_suspended_at")
        if run_error is not None:
            status = "FAILED"
        elif ctx.is_halted:
            status = "HALTED"
        elif suspended_at:
            status = "SUSPENDED"
        else:
            status = "COMPLETED"

        if args.json:
            payload = {
                "session_id": ctx.session_id,
                "status": status,
                "is_halted": ctx.is_halted,
                "halt_reason": ctx.halt_reason,
                "suspended_at": suspended_at,
                "steps": len(ctx.trajectory),
                "state": ctx.state,
                "trace_out": str(args.trace_out) if args.trace_out else None,
                "latest_checkpoint_id": latest_cp.checkpoint_id if latest_cp else None,
                "error": run_error,
            }
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        else:
            print(f"AutoCetacean Run [{status}] session={ctx.session_id} steps={len(ctx.trajectory)}")
            if suspended_at:
                print(f"Suspended at gate: {suspended_at} (pass --approve-gates to continue)")
            if latest_cp:
                print(f"Latest checkpoint: {latest_cp.checkpoint_id}")
            if args.trace_out:
                print(f"Trace exported: {args.trace_out}")
            if run_error:
                print(f"autocetacean: execution failed: {run_error}", file=sys.stderr)
            elif ctx.is_halted and ctx.halt_reason:
                print(f"autocetacean: execution halted: {ctx.halt_reason}", file=sys.stderr)

        if run_error is not None or ctx.is_halted:
            return 1
        return 0

    if args.command == "demo":
        report = run_demo(quiet=args.json)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if report["passed"] else 1

    if args.command == "guard":
        try:
            guard = SubprocessToolGuard(args.workspace, timeout=args.timeout, gate_timeout=args.gate_timeout)
            outcome = guard.run(args.cmd, gate_cmd=args.gate, trace_out=args.trace_out)
        except (OSError, WorkspaceGuardError) as exc:
            print(f"autocetacean: guard error: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(outcome.to_dict(), indent=2, ensure_ascii=False))
        else:
            verdict = "PASSED" if outcome.passed else ("TIMED_OUT" if outcome.timed_out else "ROLLED_BACK")
            print(f"AutoCetacean Guard [{verdict}] cmd_rc={outcome.cmd_returncode} gate_rc={outcome.gate_returncode} rolled_back={outcome.rolled_back}")
        return 0 if outcome.passed else 1

    if args.command == "mcp-record":
        cmd_tokens = list(args.server_cmd or [])
        if cmd_tokens and cmd_tokens[0] == "--":
            cmd_tokens = cmd_tokens[1:]
        if not cmd_tokens:
            print("autocetacean: mcp-record requires server command after '--'", file=sys.stderr)
            return 2
        try:
            MCPStdioRecorder(cmd_tokens, cwd=args.cwd).record(args.trace)
        except OSError as exc:
            print(f"autocetacean: mcp-record failed: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "mcp-replay":
        try:
            replayer = MCPStdioReplayer.from_trace(args.trace, strict=args.strict)
        except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            print(f"autocetacean: unable to load MCP trace: {exc}", file=sys.stderr)
            return 2
        mismatches = replayer.serve_stdio()
        return 1 if (args.strict and mismatches) else 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
