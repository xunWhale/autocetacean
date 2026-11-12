import json
from pathlib import Path

import pytest

from autocetacean import ExecutionContext, LayerKind, ReplayEngine
from autocetacean.cli import main
from autocetacean.replay import ReplayError


def event(step, node, before, after, status="SUCCESS", timestamp=None, **extra):
    return {"step_index": step, "timestamp": timestamp or step, "node_name": node,
            "state_before": before, "state_after": after, "action": "run",
            "status": status, **extra}


def test_linear_trace_replay_and_summary():
    replay = ReplayEngine.from_events([
        event(1, "retrieve", {}, {"docs": 1}),
        event(2, "answer", {"docs": 1}, {"answer": "ok"}),
    ])
    summary = replay.export_summary()
    assert summary["total_steps"] == 2
    assert summary["successful_steps"] == 2
    assert summary["rollback_count"] == 0
    output = replay.render_terminal("plain")
    assert "retrieve" in output and "answer" in output and "SUCCESS" in output
    assert "\x1b[" not in output


def test_self_healing_trace_renders_retry_rollback_and_checkpoint():
    replay = ReplayEngine.from_events([
        event(1, "worker", {"n": 0}, {"n": 1}, status="SUCCESS", checkpoint_id="cp_1"),
        event(2, "worker", {"n": 1}, {"n": 2}, status="RETRY", error_message="temporary", checkpoint_id="cp_1"),
        event(3, "worker", {"n": 1}, {"n": 2}, status="ROLLBACK", checkpoint_id="cp_1"),
        event(4, "worker", {"n": 1}, {"n": 3}, status="SUCCESS", checkpoint_id="cp_2"),
    ])
    rendered = replay.render_terminal("plain")
    assert "RETRY" in rendered and "ROLLBACK" in rendered and "cp_1" in rendered
    assert replay.export_summary()["self_healing_convergence_rate"] == 1.0


def test_json_and_jsonl_loading(tmp_path):
    trace = [event(1, "a", {}, {"x": 1})]
    json_path = tmp_path / "trace.json"
    json_path.write_text(json.dumps({"events": trace}), encoding="utf-8")
    assert ReplayEngine(json_path).export_summary()["total_steps"] == 1
    jsonl_path = tmp_path / "trace.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(item) for item in trace), encoding="utf-8")
    assert ReplayEngine(jsonl_path).export_summary()["total_steps"] == 1


def test_context_loading():
    context = ExecutionContext(session_id="s1", state={"x": 1})
    context.record_step("one", LayerKind.LAYER_5_GRAPH, {"x": 1}, {"x": 2})
    replay = ReplayEngine(context)
    assert replay.records[0]["node_name"] == "one"
    assert replay.records[0]["status"] == "SUCCESS"


def test_html_export_is_standalone(tmp_path):
    output = tmp_path / "replay.html"
    ReplayEngine.from_events([event(1, "a", {}, {"ok": True})]).export_html(output)
    text = output.read_text(encoding="utf-8")
    assert "<!doctype html>" in text
    assert "State diff" in text
    assert "a" in text


def test_cli_replay_json_plain_html_and_errors(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps(event(1, "start", {}, {"ready": True})), encoding="utf-8")
    html_path = tmp_path / "out.html"
    assert main(["replay", str(trace), "--json", "--html", str(html_path)]) == 0
    assert json.loads(capsys.readouterr().out)["total_steps"] == 1
    assert html_path.exists()
    assert main(["replay", str(trace), "--plain"]) == 0
    assert "\x1b[" not in capsys.readouterr().out
    assert main(["replay", str(tmp_path / "missing.json")]) == 2
    assert "not found" in capsys.readouterr().err


def test_empty_and_invalid_files_fail_cleanly(tmp_path, capsys):
    empty = tmp_path / "empty.json"
    empty.write_text("", encoding="utf-8")
    assert main(["replay", str(empty)]) == 2
    assert "empty" in capsys.readouterr().err
    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text('{"step_index": 1}\nnot-json', encoding="utf-8")
    assert main(["replay", str(invalid)]) == 2
    assert "invalid JSON/JSONL" in capsys.readouterr().err


def test_invalid_status_is_rejected():
    with pytest.raises(ReplayError, match="invalid status"):
        ReplayEngine.from_events([event(1, "x", {}, {}, status="BROKEN")])
