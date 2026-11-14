import json
from pathlib import Path
import pytest

from autocetacean import (
    CheckpointManager,
    ExecutionContext,
    GraphExecutionError,
    GraphVisualizer,
    Layer4LoopController,
    LayerKind,
    ReplayEngine,
    StateGraph,
)
from autocetacean.cli import main


def test_state_before_after_deepcopy_isolation():
    graph = StateGraph()

    def mutate_nested(ctx: ExecutionContext):
        ctx.state["nested"]["items"].append("added")
        ctx.state["nested"]["meta"]["count"] = 99
        return "mutated"

    def second_step(ctx: ExecutionContext):
        ctx.state["nested"]["items"].append("step2")
        ctx.state["second"] = True
        return "done"

    graph.add_node("first", mutate_nested, layer=LayerKind.LAYER_1_PROMPT)
    graph.add_node("second", second_step, layer=LayerKind.LAYER_5_GRAPH)
    graph.add_edge("first", "second")
    graph.set_entry_point("first")
    graph.add_finish_point("second")

    ctx = ExecutionContext(
        session_id="iso",
        state={"nested": {"items": ["init"], "meta": {"count": 1}}},
    )
    graph.run(ctx)

    step1, step2 = ctx.trajectory
    # Step 1 input_data and state_before must retain initial nested state
    assert step1.input_data["nested"] == {"items": ["init"], "meta": {"count": 1}}
    assert step1.metadata["state_before"]["nested"] == {"items": ["init"], "meta": {"count": 1}}
    assert step1.metadata["state_after"]["nested"] == {"items": ["init", "added"], "meta": {"count": 99}}

    # Step 2 mutations must not leak back into Step 1 state_after
    assert step2.metadata["state_before"]["nested"] == {"items": ["init", "added"], "meta": {"count": 99}}
    assert step2.metadata["state_after"]["nested"] == {"items": ["init", "added", "step2"], "meta": {"count": 99}}
    assert step2.metadata["state_after"]["second"] is True
    assert "second" not in step1.metadata["state_after"]


def test_step_metadata_carries_checkpoint_id_and_failure_violation():
    mgr = CheckpointManager()
    graph = StateGraph(checkpoint_manager=mgr)

    graph.add_node("ok", lambda c: c.state.update({"x": 1}) or "ok")
    graph.add_node(
        "strict",
        lambda c: "unreachable",
        layer=LayerKind.LAYER_2_CONTEXT,
        expected_schema={"required": ["user"], "properties": {"user": {"type": "string"}}},
    )
    graph.add_edge("ok", "strict")
    graph.set_entry_point("ok")

    ctx = ExecutionContext(session_id="meta_check", state={"nested": {"a": 1}})
    with pytest.raises(GraphExecutionError):
        graph.run(ctx)

    s_ok, s_fail = ctx.trajectory
    assert s_ok.metadata["status"] == "SUCCESS"
    assert s_ok.metadata["checkpoint_id"] == mgr.get_latest().checkpoint_id
    assert mgr.get_checkpoint(s_ok.metadata["checkpoint_id"]) is not None
    assert s_ok.metadata["state_before"] == {"nested": {"a": 1}}
    assert s_ok.metadata["state_after"] == {"nested": {"a": 1}, "x": 1}

    assert s_fail.metadata["status"] == "HALT"
    assert s_fail.metadata["state_before"] == {"nested": {"a": 1}, "x": 1}
    assert s_fail.metadata["state_after"] == {"nested": {"a": 1}, "x": 1}
    assert s_fail.metadata["violation"]["kind"] == "missing"
    assert s_fail.metadata["violation"]["path"] == "user"


def test_gate_resume_approved_and_conditional_routing():
    graph = StateGraph()
    graph.add_node("prep", lambda c: c.state.update({"ready": True}))
    graph.add_node("gate", lambda c: None, is_gate=True)
    graph.add_node("deploy_prod", lambda c: c.state.update({"env": "prod"}))
    graph.add_node("deploy_staging", lambda c: c.state.update({"env": "staging"}))

    graph.add_edge("prep", "gate")
    graph.add_conditional_edge(
        "gate",
        lambda c: "deploy_prod" if c.state.get("target") == "prod" else "deploy_staging",
    )
    graph.set_entry_point("prep")
    graph.add_finish_point("deploy_prod")
    graph.add_finish_point("deploy_staging")

    ctx = ExecutionContext(session_id="gate_cond", state={"target": "prod"})
    graph.run(ctx)

    assert ctx.variables.get("_suspended_at") == "gate"
    assert ctx.trajectory[-1].metadata["status"] == "SUSPENDED"
    assert ctx.trajectory[-1].metadata["checkpoint_id"] is not None

    graph.resume(ctx, approved=True)
    assert "_suspended_at" not in ctx.variables
    assert ctx.state["env"] == "prod"
    assert ctx.is_halted is False


def test_gate_resume_rejected_halts_and_records_audit_step():
    graph = StateGraph()
    graph.add_node("prep", lambda c: c.state.update({"ready": True}))
    graph.add_node("gate", lambda c: None, is_gate=True)
    graph.add_node("danger", lambda c: c.state.update({"ran": True}))

    graph.add_edge("prep", "gate")
    graph.add_edge("gate", "danger")
    graph.set_entry_point("prep")
    graph.add_finish_point("danger")

    ctx = ExecutionContext(session_id="gate_reject")
    graph.run(ctx)
    steps_before = len(ctx.trajectory)

    graph.resume(ctx, approved=False)
    assert ctx.is_halted is True
    assert ctx.halt_reason == "Gate rejected"
    assert "ran" not in ctx.state
    assert len(ctx.trajectory) == steps_before + 1
    assert ctx.trajectory[-1].error == "Gate rejected"
    assert ctx.trajectory[-1].metadata["status"] == "HALT"
    assert ctx.trajectory[-1].metadata["gate_status"] == "REJECTED"


def test_gate_resume_restore_checkpoint_reverts_corrupted_state():
    graph = StateGraph()
    graph.add_node("prep", lambda c: c.state.update({"clean": True}))
    graph.add_node("gate", lambda c: None, is_gate=True)
    graph.add_node("finish", lambda c: c.state.update({"done": True}))

    graph.add_edge("prep", "gate")
    graph.add_edge("gate", "finish")
    graph.set_entry_point("prep")
    graph.add_finish_point("finish")

    ctx = ExecutionContext(session_id="gate_restore")
    graph.run(ctx)

    # Corrupt state while suspended
    ctx.state["clean"] = False
    ctx.state["tampered"] = "bad"

    graph.resume(ctx, approved=True, restore_checkpoint=True)
    assert ctx.state["clean"] is True
    assert "tampered" not in ctx.state
    assert ctx.state["done"] is True
    assert any(step.metadata.get("status") == "ROLLBACK" for step in ctx.trajectory)


def test_reset_halt_and_run_reset_halt_flag():
    graph = StateGraph()

    def flaky(ctx: ExecutionContext):
        if not ctx.state.get("fixed"):
            raise RuntimeError("boom")
        ctx.state["ok"] = True

    graph.add_node("work", flaky)
    graph.add_node("recover", lambda c: c.state.update({"fixed": True}))
    graph.add_edge("recover", "work")
    graph.set_entry_point("work")
    graph.add_finish_point("work")

    ctx = ExecutionContext(session_id="fp1")
    with pytest.raises(GraphExecutionError):
        graph.run(ctx)
    assert ctx.is_halted is True

    # Without reset_halt, run() exits silently (FP-1 behavior preserved when False)
    graph.run(ctx, start_node="recover", reset_halt=False)
    assert ctx.state.get("fixed") is None

    # With reset_halt=True, execution resumes cleanly
    graph.run(ctx, start_node="recover", reset_halt=True)
    assert ctx.is_halted is False
    assert ctx.halt_reason is None
    assert ctx.state["ok"] is True

    # Direct ctx.reset_halt() also clears flags
    ctx.is_halted = True
    ctx.halt_reason = "manual"
    ctx.reset_halt()
    assert ctx.is_halted is False
    assert ctx.halt_reason is None


def test_checkpoint_get_and_load_from_dir_cross_process(tmp_path: Path):
    cp_dir = tmp_path / "checkpoints"

    def build():
        g = StateGraph(checkpoint_manager=CheckpointManager(storage_dir=cp_dir))
        g.add_node("step1", lambda c: c.state.update({"count": 1}))
        g.add_node("gate", lambda c: None, is_gate=True)
        g.add_node("step2", lambda c: c.state.update({"count": c.state["count"] + 10}))
        g.add_edge("step1", "gate")
        g.add_edge("gate", "step2")
        g.set_entry_point("step1")
        g.add_finish_point("step2")
        return g

    # Process 1: run until gate
    g1 = build()
    ctx1 = ExecutionContext(session_id="cross_proc")
    g1.run(ctx1)
    cp1_id = ctx1.trajectory[0].metadata["checkpoint_id"]
    cp_gate_id = ctx1.trajectory[1].metadata["checkpoint_id"]

    # Process 2: fresh CheckpointManager + fresh StateGraph
    mgr2 = CheckpointManager(storage_dir=cp_dir)
    assert mgr2.get_checkpoint(cp1_id) is not None
    assert mgr2.get_checkpoint("nonexistent_cp") is None
    latest = mgr2.load_from_dir()
    assert latest is not None
    assert latest.checkpoint_id == cp_gate_id
    assert latest.variables.get("_suspended_at") == "gate"

    g2 = build()
    ctx2 = ExecutionContext(session_id="cross_proc")
    g2.resume(ctx2, approved=True, restore_checkpoint=True)
    assert ctx2.state["count"] == 11


def test_export_trace_jsonl_and_json_roundtrip_with_replay_engine(tmp_path: Path):
    graph = StateGraph()
    ctrl = Layer4LoopController(max_retries=2)

    def retry_node(ctx: ExecutionContext):
        def op(c):
            c.variables["tries"] = c.variables.get("tries", 0) + 1
            if c.variables["tries"] == 1:
                raise ValueError("transient")
            c.state["healed"] = True
            return "healed"

        return ctrl.execute_with_retry(ctx, "retry_op", op)

    graph.add_node("heal", retry_node, layer=LayerKind.LAYER_4_LOOP)
    graph.add_node("gate", lambda c: None, is_gate=True)
    graph.add_node("end", lambda c: c.state.update({"done": True}))
    graph.add_edge("heal", "gate")
    graph.add_edge("gate", "end")
    graph.set_entry_point("heal")
    graph.add_finish_point("end")

    ctx = ExecutionContext(session_id="trace_rt")
    graph.run(ctx)
    graph.resume(ctx, approved=True)

    jsonl_path = ctx.export_trace(tmp_path / "trace.jsonl", format="jsonl")
    json_path = ctx.export_trace(tmp_path / "trace.json", format="json")

    required_keys = {
        "step_index",
        "timestamp",
        "node_name",
        "state_before",
        "state_after",
        "action",
        "status",
        "error_message",
        "checkpoint_id",
        "duration_ms",
        "metadata",
    }
    first_line = json.loads(jsonl_path.read_text(encoding="utf-8").splitlines()[0])
    assert required_keys.issubset(first_line.keys())

    r_jsonl = ReplayEngine(jsonl_path)
    r_json = ReplayEngine(json_path)
    assert r_jsonl.export_summary()["total_steps"] == len(ctx.trajectory)
    assert r_json.export_summary()["total_steps"] == len(ctx.trajectory)
    assert r_jsonl.export_summary()["retry_count"] == 1
    assert r_jsonl.export_summary()["suspended_count"] == 1
    assert r_jsonl.export_summary()["self_healing_convergence_rate"] == 1.0

    rendered = r_jsonl.render_terminal("plain")
    assert "SUSPENDED" in rendered
    assert "RETRY" in rendered
    assert "SUCCESS" in rendered

    with pytest.raises(ValueError):
        ctx.export_trace(tmp_path / "bad.txt", format="yaml")


def test_cli_run_with_factory_callable_and_gate_options(tmp_path: Path, capsys):
    workflow = tmp_path / "my_workflow.py"
    workflow.write_text(
        "from autocetacean import ExecutionContext, LayerKind, StateGraph\n"
        "\n"
        "def build_graph():\n"
        "    g = StateGraph()\n"
        "    g.add_node('start', lambda c: c.state.update({'step': 1}),\n"
        "               layer=LayerKind.LAYER_2_CONTEXT,\n"
        "               expected_schema={'required': ['topic'], 'properties': {'topic': {'type': 'string'}}})\n"
        "    g.add_node('gate', lambda c: None, is_gate=True)\n"
        "    g.add_node('finish', lambda c: c.state.update({'done': True}))\n"
        "    g.add_edge('start', 'gate')\n"
        "    g.add_edge('gate', 'finish')\n"
        "    g.set_entry_point('start')\n"
        "    g.add_finish_point('finish')\n"
        "    return g\n"
        "\n"
        "def run_with_ctx(ctx: ExecutionContext):\n"
        "    ctx.state['via_ctx'] = True\n"
        "    return build_graph()\n",
        encoding="utf-8",
    )

    input_file = tmp_path / "input.json"
    input_file.write_text('{"topic": "ocean"}', encoding="utf-8")
    trace_suspended = tmp_path / "suspended.jsonl"
    trace_done = tmp_path / "done.jsonl"
    cp_dir = tmp_path / "cps"

    # 1. Pause at gate without --approve-gates
    rc1 = main([
        "run",
        f"{workflow}:build_graph",
        "--input",
        f"@{input_file}",
        "--checkpoint-dir",
        str(cp_dir),
        "--trace-out",
        str(trace_suspended),
        "--json",
    ])
    assert rc1 == 0
    out1 = json.loads(capsys.readouterr().out)
    assert out1["status"] == "SUSPENDED"
    assert out1["suspended_at"] == "gate"
    assert out1["steps"] == 2
    assert list(cp_dir.glob("*.json"))

    # 2. Auto-approve gate with --approve-gates and (ctx) callable target
    rc2 = main([
        "run",
        f"{workflow}:run_with_ctx",
        "--input",
        '{"topic": "whale"}',
        "--trace-out",
        str(trace_done),
        "--approve-gates",
        "--json",
    ])
    assert rc2 == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["status"] == "COMPLETED"
    assert out2["state"]["done"] is True
    assert out2["state"]["via_ctx"] is True
    assert ReplayEngine(trace_done).export_summary()["successful_steps"] == 2

    # 3. Failure path (schema error -> exit code 1, trace still exported!)
    trace_err = tmp_path / "err.jsonl"
    rc3 = main([
        "run",
        f"{workflow}:build_graph",
        "--input",
        '{"topic": 123}',
        "--trace-out",
        str(trace_err),
    ])
    assert rc3 == 1
    capsys.readouterr()
    assert trace_err.exists()
    assert ReplayEngine(trace_err).export_summary()["violation_kinds"] == {"type_mismatch": 1}

    # 4. Invalid CLI args -> exit code 2
    assert main(["run", f"{workflow}:build_graph", "--input", "not-json"]) == 2
    assert main(["run", f"{workflow}:build_graph", "--input", "@missing_input.json"]) == 2
    assert main(["run", "missing_mod:graph"]) == 2
    capsys.readouterr()


def test_cli_graph_with_trace_overlay(tmp_path: Path, capsys):
    trace_path = tmp_path / "trace.jsonl"
    rc_run = main([
        "run",
        "examples.self_healing_agent:graph",
        "--input",
        '{"bug_report": "overflow", "target_file": "scanner.c"}',
        "--approve-gates",
        "--trace-out",
        str(trace_path),
    ])
    assert rc_run == 0
    capsys.readouterr()

    rc_graph = main([
        "graph",
        "examples.self_healing_agent:graph",
        "--trace",
        str(trace_path),
    ])
    assert rc_graph == 0
    mermaid_out = capsys.readouterr().out
    assert "trace_success" in mermaid_out
    assert "SUCCESS x1" in mermaid_out

    html_path = tmp_path / "traced.html"
    rc_html = main([
        "graph",
        "examples.self_healing_agent:graph",
        "--trace",
        str(trace_path),
        "--format",
        "html",
        "--output",
        str(html_path),
    ])
    assert rc_html == 0
    html_text = html_path.read_text(encoding="utf-8")
    assert "Trace overlay:" in html_text

    # Missing trace file -> exit 2
    assert main(["graph", "examples.self_healing_agent:graph", "--trace", str(tmp_path / "nope.jsonl")]) == 2
    capsys.readouterr()
