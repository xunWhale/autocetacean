"""End-to-end demo of AutoCetacean v0.3.0 workspace rollback guard & MCP stdio replay."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

from autocetacean import MCPStdioRecorder, MCPStdioReplayer, SubprocessToolGuard

ECHO_MCP_SERVER = """
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    method, rid = req.get("method"), req.get("id")
    if method == "initialize":
        res = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}}
    elif method == "tools/list":
        res = {"tools": [{"name": "add", "description": "Add two numbers"}]}
    elif method == "tools/call":
        args = req.get("params", {}).get("arguments", {})
        res = {"content": [{"type": "text", "text": str(args.get("a", 0) + args.get("b", 0))}]}
    else:
        res = {}
    if rid is not None:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}) + "\\n")
        sys.stdout.flush()
"""


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ac_demo_") as tmp:
        root = Path(tmp)
        ws = root / "repo"
        ws.mkdir()
        (ws / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        (ws / "test_calc.py").write_text(
            "import unittest\nfrom calc import add\n\nclass T(unittest.TestCase):\n"
            "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n",
            encoding="utf-8",
        )
        guard = SubprocessToolGuard(ws)
        bad = guard.run(
            [sys.executable, "-c", "from pathlib import Path; Path('calc.py').write_text('def add(a,b): return 0\\n'); Path('junk.txt').write_text('x')"],
            gate_cmd=[sys.executable, "-m", "unittest", "test_calc.py"],
            trace_out=root / "bad_trace.json",
        )
        assert bad.rolled_back and not bad.passed and not (ws / "junk.txt").exists()
        print(f"[1] Bad edit rolled back: changes={bad.changes}")

        good = guard.run(
            [sys.executable, "-c", "from pathlib import Path; Path('calc.py').write_text('def add(a, b):\\n    return a + b\\n')"],
            gate_cmd=[sys.executable, "-m", "unittest", "test_calc.py"],
        )
        assert good.passed and not good.rolled_back
        print(f"[2] Good edit committed: changes={good.changes}")

        trace = root / "mcp.jsonl"
        reqs = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "demo"}}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "add", "arguments": {"a": 7, "b": 5}}}),
        ]) + "\n"
        entries = MCPStdioRecorder([sys.executable, "-c", ECHO_MCP_SERVER]).record(
            trace, client_in=io.BytesIO(reqs.encode()), client_out=io.BytesIO()
        )
        print(f"[3] Recorded {len(entries)} MCP exchanges -> {trace.name}")

        replay_in = io.BytesIO((
            json.dumps({"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {"name": "add", "arguments": {"a": 7, "b": 5}}}) + "\n"
            + json.dumps({"jsonrpc": "2.0", "id": 100, "method": "tools/call", "params": {"name": "add", "arguments": {"a": 7, "b": 999}}}) + "\n"
        ).encode())
        replay_out = io.BytesIO()
        mismatches = MCPStdioReplayer.from_trace(trace, strict=True).serve_stdio(client_in=replay_in, client_out=replay_out)
        lines = [json.loads(x) for x in replay_out.getvalue().decode().splitlines()]
        assert lines[0]["id"] == 99 and lines[0]["result"]["content"][0]["text"] == "12"
        assert lines[1]["error"]["code"] == -32602 and len(mismatches) == 1
        print("[4] Offline replay ok (id=99 -> 12), strict guard caught drift (id=100 -> -32602)")


if __name__ == "__main__":
    main()
