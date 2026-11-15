from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

from autocetacean import MCPStdioRecorder, MCPStdioReplayer, load_mcp_trace

SERVER_SCRIPT = """
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line: continue
    req = json.loads(line)
    m, rid = req.get("method"), req.get("id")
    if m == "initialize": res = {"protocolVersion": "2024-11-05"}
    elif m == "tools/call":
        args = req.get("params", {}).get("arguments", {})
        res = {"sum": args.get("a", 0) + args.get("b", 0)}
    else: res = {"echo": m}
    if rid is not None:
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}) + "\\n")
        sys.stdout.flush()
"""


def test_mcp_record_and_offline_strict_replay(tmp_path: Path) -> None:
    srv = tmp_path / "srv.py"
    srv.write_text(SERVER_SCRIPT, encoding="utf-8")
    trace = tmp_path / "session.jsonl"
    reqs = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"v": 1}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "add", "arguments": {"a": 3, "b": 4}}}),
    ]) + "\n"
    entries = MCPStdioRecorder([sys.executable, str(srv)]).record(trace, client_in=io.BytesIO(reqs.encode()), client_out=io.BytesIO())
    loaded = load_mcp_trace(trace)
    assert len(entries) == 3 and [e.method for e in loaded if e.direction == "request_response"] == ["initialize", "tools/call"]
    assert any(e.method == "notifications/initialized" for e in loaded)
    srv.unlink()

    replay_in = io.BytesIO((
        json.dumps({"jsonrpc": "2.0", "id": "r1", "method": "initialize", "params": {"v": 1}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": "r2", "method": "tools/call", "params": {"name": "add", "arguments": {"a": 3, "b": 4}}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": "r3", "method": "tools/call", "params": {"name": "add", "arguments": {"a": 3, "b": 99}}}) + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": "r4", "method": "tools/unknown", "params": {}}) + "\n"
    ).encode())
    replay_out = io.BytesIO()
    mismatches = MCPStdioReplayer.from_trace(trace, strict=True).serve_stdio(client_in=replay_in, client_out=replay_out)
    resps = [json.loads(x) for x in replay_out.getvalue().decode().splitlines()]
    assert resps[0]["result"] == {"protocolVersion": "2024-11-05"}
    assert resps[1]["result"] == {"sum": 7}
    assert resps[2]["error"]["code"] == -32602
    assert resps[3]["error"]["code"] == -32601
    assert len(mismatches) == 2


def test_cli_mcp_record_and_replay_subprocesses(tmp_path: Path) -> None:
    srv = tmp_path / "srv.py"
    srv.write_text(SERVER_SCRIPT, encoding="utf-8")
    trace = tmp_path / "cli.jsonl"
    env = {"PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")}
    req = json.dumps({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "add", "arguments": {"a": 9, "b": 1}}}) + "\n"
    rec = subprocess.run([sys.executable, "-m", "autocetacean.cli", "mcp-record", "--trace", str(trace), "--", sys.executable, str(srv)], input=req, text=True, capture_output=True, env=env, check=True)
    assert json.loads(rec.stdout)["result"] == {"sum": 10}
    rep_ok = subprocess.run([sys.executable, "-m", "autocetacean.cli", "mcp-replay", "--trace", str(trace), "--strict"], input=req, text=True, capture_output=True, env=env, check=True)
    assert json.loads(rep_ok.stdout)["result"] == {"sum": 10}
    bad_req = json.dumps({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "add", "arguments": {"a": 0, "b": 0}}}) + "\n"
    rep_bad = subprocess.run([sys.executable, "-m", "autocetacean.cli", "mcp-replay", "--trace", str(trace), "--strict"], input=bad_req, text=True, capture_output=True, env=env)
    assert rep_bad.returncode == 1 and json.loads(rep_bad.stdout)["error"]["code"] == -32602
