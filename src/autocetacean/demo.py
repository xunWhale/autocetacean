"""One-command self-contained demonstration of AutoCetacean's guarantees."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from autocetacean.mcp_proxy import MCPStdioRecorder, MCPStdioReplayer
from autocetacean.workspace import SubprocessToolGuard, WorkspaceTransaction

PASS_LINE = "AutoCetacean demo: ALL CHECKS PASSED (guard rollback + mcp replay)"

_ECHO_SERVER = """
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        res = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    elif method == "tools/call":
        args = req.get("params", {}).get("arguments", {})
        res = {"content": [{"type": "text", "text": str(args.get("a", 0) + args.get("b", 0))}]}
    else:
        res = {}
    if rid is not None:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}) + "\\n")
        sys.stdout.flush()
"""


def _demo_guard(root: Path) -> dict[str, Any]:
    ws = root / "guard_demo"
    ws.mkdir()
    (ws / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (ws / "test_calc.py").write_text(
        "import unittest\nfrom calc import add\n\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n",
        encoding="utf-8",
    )

    guard = SubprocessToolGuard(ws)
    outcome = guard.run(
        [sys.executable, "-c",
         "from pathlib import Path; Path('calc.py').write_text('def add(a, b):\\n    return 0\\n'); Path('junk.txt').write_text('x')"],
        gate_cmd=[sys.executable, "-m", "unittest", "test_calc.py"],
        trace_out=root / "guard_trace.json",
    )

    restored = (ws / "calc.py").read_text(encoding="utf-8")
    junk_gone = not (ws / "junk.txt").exists()
    ok = outcome.rolled_back and not outcome.passed and junk_gone and "return a + b" in restored
    return {
        "name": "workspace_guard_rollback",
        "passed": ok,
        "rolled_back": outcome.rolled_back,
        "gate_returncode": outcome.gate_returncode,
        "changes": outcome.changes,
        "restored_source": restored,
        "junk_removed": junk_gone,
    }


def _demo_mcp(root: Path) -> dict[str, Any]:
    trace = root / "mcp_demo.jsonl"
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"clientInfo": {"name": "autocetacean-demo"}}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                        "params": {"name": "add", "arguments": {"a": 7, "b": 5}}}),
        ]
    ) + "\n"

    entries = MCPStdioRecorder([sys.executable, "-c", _ECHO_SERVER]).record(
        trace,
        client_in=io.BytesIO(requests.encode("utf-8")),
        client_out=io.BytesIO(),
    )

    replay_in = io.BytesIO(
        (
            json.dumps({"jsonrpc": "2.0", "id": 99, "method": "tools/call",
                        "params": {"name": "add", "arguments": {"a": 7, "b": 5}}}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 100, "method": "tools/call",
                          "params": {"name": "add", "arguments": {"a": 7, "b": 999}}}) + "\n"
        ).encode("utf-8")
    )
    replay_out = io.BytesIO()
    replayer = MCPStdioReplayer.from_trace(trace, strict=True)
    mismatches = replayer.serve_stdio(client_in=replay_in, client_out=replay_out)
    responses = [json.loads(line) for line in replay_out.getvalue().decode("utf-8").splitlines()]

    matched_text = responses[0].get("result", {}).get("content", [{}])[0].get("text")
    drift_code = responses[1].get("error", {}).get("code")
    ok = (
        len(entries) >= 2
        and matched_text == "12"
        and drift_code == -32602
        and len(mismatches) == 1
    )
    return {
        "name": "mcp_record_and_offline_replay",
        "passed": ok,
        "recorded_exchanges": len(entries),
        "replayed_matched_value": matched_text,
        "drift_error_code": drift_code,
        "mismatch_count": len(mismatches),
    }


def run_demo(quiet: bool = False) -> dict[str, Any]:
    """Run both self-contained demonstrations and return a structured report."""
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="autocetacean_demo_") as tmp:
        root = Path(tmp)
        checks.append(_demo_guard(root))
        checks.append(_demo_mcp(root))

    passed = all(check["passed"] for check in checks)
    report = {"passed": passed, "checks": checks}
    if not quiet:
        print("AutoCetacean demo — two guarantees, one command, no external dependencies\n")
        for check in checks:
            mark = "PASS" if check["passed"] else "FAIL"
            print(f"[{mark}] {check['name']}")
            if check["name"] == "workspace_guard_rollback":
                print(f"       gate exit code: {check['gate_returncode']}")
                print(f"       rolled back:    {check['rolled_back']}")
                print(f"       changed files:  {check['changes']}")
                print(f"       junk removed:   {check['junk_removed']}")
                print(f"       restored:       {check['restored_source'].splitlines()[1].strip()!r}")
            else:
                print(f"       recorded exchanges: {check['recorded_exchanges']}")
                print(f"       replayed value:     {check['replayed_matched_value']}")
                print(f"       drift error code:   {check['drift_error_code']}")
                print(f"       mismatches caught:  {check['mismatch_count']}")
            print()
        if passed:
            print(PASS_LINE)
        else:
            print("AutoCetacean demo: FAILED — see the failing check above", file=sys.stderr)
    return report


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``autocetacean demo``."""
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    report = run_demo(quiet=as_json)
    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
