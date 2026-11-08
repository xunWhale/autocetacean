import pytest

from autocetacean.graph import GraphExecutionError, StateGraph
from autocetacean.layers import SchemaValidationError
from autocetacean.types import ExecutionContext, LayerKind


def test_linear_graph_execution():
    graph = StateGraph()

    def step1(ctx):
        ctx.state["v"] = 1
        return "ok1"

    def step2(ctx):
        ctx.state["v"] += 1
        return "ok2"

    graph.add_node("step1", step1)
    graph.add_node("step2", step2)
    graph.add_edge("step1", "step2")
    graph.set_entry_point("step1")
    graph.add_finish_point("step2")

    ctx = ExecutionContext(session_id="s1")
    graph.run(ctx)

    assert ctx.state["v"] == 2
    assert len(ctx.trajectory) == 2


def test_conditional_routing_edge():
    graph = StateGraph()

    graph.add_node("decide", lambda c: None)
    graph.add_node("branch_even", lambda c: c.state.update({"res": "even"}))
    graph.add_node("branch_odd", lambda c: c.state.update({"res": "odd"}))

    def router(c):
        return "branch_even" if c.state.get("num", 0) % 2 == 0 else "branch_odd"

    graph.add_conditional_edge("decide", router)
    graph.set_entry_point("decide")
    graph.add_finish_point("branch_even")
    graph.add_finish_point("branch_odd")

    ctx_even = ExecutionContext(session_id="s_even", state={"num": 4})
    graph.run(ctx_even)
    assert ctx_even.state["res"] == "even"

    ctx_odd = ExecutionContext(session_id="s_odd", state={"num": 7})
    graph.run(ctx_odd)
    assert ctx_odd.state["res"] == "odd"


def test_node_schema_validation_rejection():
    graph = StateGraph()
    schema = {"required": ["target_ip"]}

    graph.add_node("deploy", lambda c: "done", expected_schema=schema)
    graph.set_entry_point("deploy")

    ctx = ExecutionContext(session_id="s_err", state={})
    with pytest.raises(GraphExecutionError) as exc:
        graph.run(ctx)
    assert "Missing required schema property" in str(exc.value)


def test_gate_suspends_execution():
    graph = StateGraph()
    graph.add_node("prepare", lambda c: c.state.update({"ready": True}))
    graph.add_node("human_gate", lambda c: None, is_gate=True)
    graph.add_node("execute_danger", lambda c: c.state.update({"executed": True}))

    graph.add_edge("prepare", "human_gate")
    graph.add_edge("human_gate", "execute_danger")
    graph.set_entry_point("prepare")
    graph.add_finish_point("execute_danger")

    ctx = ExecutionContext(session_id="s_gate")
    graph.run(ctx)

    assert ctx.state.get("ready") is True
    assert ctx.variables.get("_suspended_at") == "human_gate"
    assert ctx.state.get("executed") is None

    # Resume after approval
    graph.run(ctx, start_node="execute_danger")
    assert ctx.state.get("executed") is True


def test_duplicate_node_rejected():
    graph = StateGraph()
    graph.add_node("a", lambda c: None)
    with pytest.raises(GraphExecutionError):
        graph.add_node("a", lambda c: None)


def test_route_to_unknown_node_raises():
    graph = StateGraph()
    graph.add_node("start", lambda c: None)
    graph.add_edge("start", "phantom_node")
    graph.set_entry_point("start")

    ctx = ExecutionContext(session_id="s1")
    with pytest.raises(GraphExecutionError) as exc:
        graph.run(ctx)
    assert "Route to unknown node" in str(exc.value)


def test_max_step_limit_halts():
    graph = StateGraph()
    graph.add_node("a", lambda c: None)
    graph.add_node("b", lambda c: None)
    graph.add_edge("a", "b")
    graph.add_edge("b", "a")
    graph.set_entry_point("a")

    ctx = ExecutionContext(session_id="s1", max_steps=5)
    graph.run(ctx)
    assert ctx.is_halted is True
    assert "Max step limit reached" in ctx.halt_reason
