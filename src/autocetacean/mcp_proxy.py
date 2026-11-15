"""Zero-dependency MCP stdio JSON-RPC 2.0 recorder and offline deterministic replayer."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO, Mapping, Sequence


class MCPReplayMismatchError(RuntimeError):
    """Raised when an offline replay encounters an unmatched call in strict mode."""


@dataclass
class MCPTraceEntry:
    """Single recorded MCP JSON-RPC 2.0 request/response or notification entry."""

    seq: int
    direction: str
    method: str
    params: Any = None
    response_result: Any = None
    response_error: Any = None
    latency_ms: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MCPTraceEntry":
        return cls(
            seq=int(data["seq"]),
            direction=str(data.get("direction", "request_response")),
            method=str(data["method"]),
            params=data.get("params"),
            response_result=data.get("response_result"),
            response_error=data.get("response_error"),
            latency_ms=float(data.get("latency_ms", 0.0)),
        )


def load_mcp_trace(trace_path: str | Path) -> list[MCPTraceEntry]:
    entries: list[MCPTraceEntry] = []
    for raw in Path(trace_path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        entries.append(MCPTraceEntry.from_dict(json.loads(line)))
    return entries


class MCPStdioRecorder:
    """Transparent stdio JSON-RPC 2.0 proxy that records live MCP server exchanges."""

    def __init__(
        self,
        server_cmd: Sequence[str] | str,
        *,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        shutdown_timeout: float = 5.0,
    ) -> None:
        self.server_cmd = server_cmd
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env else None
        self.shutdown_timeout = shutdown_timeout

    def record(
        self,
        trace_path: str | Path,
        *,
        client_in: BinaryIO | None = None,
        client_out: BinaryIO | None = None,
    ) -> list[MCPTraceEntry]:
        in_stream = client_in if client_in is not None else sys.stdin.buffer
        out_stream = client_out if client_out is not None else sys.stdout.buffer
        trace_file = Path(trace_path)
        trace_file.parent.mkdir(parents=True, exist_ok=True)

        merged_env = os.environ.copy()
        if self.env:
            merged_env.update(self.env)

        proc = subprocess.Popen(
            self.server_cmd,
            cwd=self.cwd,
            env=merged_env,
            shell=isinstance(self.server_cmd, str),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
        )
        assert proc.stdin is not None and proc.stdout is not None

        lock = threading.Lock()
        pending: dict[str, tuple[str, Any, float]] = {}
        entries: list[MCPTraceEntry] = []
        seq = 0

        def _append_entry(entry: MCPTraceEntry) -> None:
            with lock:
                entries.append(entry)
            with trace_file.open("a", encoding="utf-8") as fh:
                fh.write(entry.to_json() + "\n")

        trace_file.write_text("", encoding="utf-8")

        def _pump_server_stdout() -> None:
            nonlocal seq
            assert proc.stdout is not None
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                out_stream.write(line)
                out_stream.flush()
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if "id" in msg and msg["id"] is not None:
                    key = json.dumps(msg["id"], sort_keys=True)
                    with lock:
                        req_info = pending.pop(key, None)
                    if req_info is not None:
                        method, params, t0 = req_info
                        with lock:
                            seq += 1
                            cur_seq = seq
                        _append_entry(
                            MCPTraceEntry(
                                seq=cur_seq,
                                direction="request_response",
                                method=method,
                                params=params,
                                response_result=msg.get("result"),
                                response_error=msg.get("error"),
                                latency_ms=round((time.monotonic() - t0) * 1000.0, 2),
                            )
                        )
                elif "method" in msg:
                    with lock:
                        seq += 1
                        cur_seq = seq
                    _append_entry(
                        MCPTraceEntry(
                            seq=cur_seq,
                            direction="notification",
                            method=str(msg["method"]),
                            params=msg.get("params"),
                        )
                    )

        reader = threading.Thread(target=_pump_server_stdout, daemon=True)
        reader.start()
        try:
            while True:
                line = in_stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    try:
                        msg = json.loads(text)
                        if isinstance(msg, dict) and "method" in msg:
                            if "id" in msg and msg["id"] is not None:
                                key = json.dumps(msg["id"], sort_keys=True)
                                with lock:
                                    pending[key] = (str(msg["method"]), msg.get("params"), time.monotonic())
                            else:
                                with lock:
                                    seq += 1
                                    cur_seq = seq
                                _append_entry(
                                    MCPTraceEntry(
                                        seq=cur_seq,
                                        direction="client_notification",
                                        method=str(msg["method"]),
                                        params=msg.get("params"),
                                    )
                                )
                    except json.JSONDecodeError:
                        pass
                proc.stdin.write(line)
                proc.stdin.flush()
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
            reader.join(timeout=self.shutdown_timeout)
            try:
                proc.wait(timeout=self.shutdown_timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        return entries


def _norm_params(params: Any) -> Any:
    return {} if params is None else params


class MCPStdioReplayer:
    """Offline deterministic JSON-RPC 2.0 MCP server backed by a recorded trace."""

    def __init__(self, entries: Sequence[MCPTraceEntry], *, strict: bool = True) -> None:
        self.entries = [e for e in entries if e.direction == "request_response"]
        self.strict = strict
        self._consumed: set[int] = set()
        self.mismatches: list[dict[str, Any]] = []
        self.calls_replayed = 0

    @classmethod
    def from_trace(cls, trace_path: str | Path, *, strict: bool = True) -> "MCPStdioReplayer":
        return cls(load_mcp_trace(trace_path), strict=strict)

    def _find_match(self, method: str, params: Any) -> tuple[MCPTraceEntry | None, str]:
        norm = _norm_params(params)
        same_method = [e for e in self.entries if e.method == method]
        if not same_method:
            return None, "unknown_method"
        exact = [e for e in same_method if _norm_params(e.params) == norm]
        for entry in exact:
            if entry.seq not in self._consumed:
                return entry, "exact"
        if exact:
            return exact[-1], "exact"
        if method == "tools/call" and isinstance(norm, dict):
            tool_name = norm.get("name")
            same_tool = [e for e in same_method if isinstance(e.params, dict) and e.params.get("name") == tool_name]
            if not same_tool:
                return None, "unknown_tool"
            if not self.strict:
                for entry in same_tool:
                    if entry.seq not in self._consumed:
                        return entry, "relaxed_tool"
                return same_tool[-1], "relaxed_tool"
            return None, "params_mismatch"
        if not self.strict:
            for entry in same_method:
                if entry.seq not in self._consumed:
                    return entry, "relaxed_method"
            return same_method[-1], "relaxed_method"
        return None, "params_mismatch"

    def handle_message(self, msg: Mapping[str, Any]) -> dict[str, Any] | None:
        if "id" not in msg or msg["id"] is None:
            return None
        req_id = msg["id"]
        method = str(msg.get("method", ""))
        params = msg.get("params")
        entry, reason = self._find_match(method, params)
        if entry is None:
            code = -32602 if reason == "params_mismatch" else -32601
            mismatch = {"method": method, "params": params, "reason": reason, "id": req_id}
            self.mismatches.append(mismatch)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": code,
                    "message": f"MCP replay mismatch ({reason}) for method {method!r}",
                    "data": mismatch,
                },
            }
        self._consumed.add(entry.seq)
        self.calls_replayed += 1
        if entry.response_error is not None:
            return {"jsonrpc": "2.0", "id": req_id, "error": copy.deepcopy(entry.response_error)}
        return {"jsonrpc": "2.0", "id": req_id, "result": copy.deepcopy(entry.response_result)}

    def serve_stdio(
        self,
        *,
        client_in: BinaryIO | None = None,
        client_out: BinaryIO | None = None,
    ) -> list[dict[str, Any]]:
        in_stream = client_in if client_in is not None else sys.stdin.buffer
        out_stream = client_out if client_out is not None else sys.stdout.buffer
        while True:
            line = in_stream.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError as exc:
                err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
                out_stream.write((json.dumps(err) + "\n").encode("utf-8"))
                out_stream.flush()
                continue
            if not isinstance(msg, dict):
                continue
            resp = self.handle_message(msg)
            if resp is not None:
                out_stream.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
                out_stream.flush()
        return list(self.mismatches)
