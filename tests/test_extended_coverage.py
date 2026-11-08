import pytest

from autocetacean import (
    CheckpointManager,
    ExecutionContext,
    GraphExecutionError,
    LayerKind,
    NodeStatus,
    PersistentLedger,
    StateGraph,
)
from autocetacean.layers import Layer2ContextValidator, SchemaValidationError


def test_state_machine_counter_loop():
    graph = StateGraph()

    def increment(ctx):
        ctx.state["count"] = ctx.state.get("count", 0) + 1

    def should_continue(ctx):
        return "increment" if ctx.state["count"] < 3 else "done"

    graph.add_node("increment", increment)
    graph.add_node("done", lambda c: c.state.update({"finished": True}))
    graph.add_conditional_edge("increment", should_continue)
    graph.set_entry_point("increment")
    graph.add_finish_point("done")

    ctx = ExecutionContext(session_id="counter_loop")
    graph.run(ctx)
    assert ctx.state["count"] == 3
    assert ctx.state["finished"] is True


def test_execution_context_record_step():
    ctx = ExecutionContext(session_id="ctx_rec")
    step = ctx.record_step(
        node_name="test_node",
        layer=LayerKind.LAYER_1_PROMPT,
        input_data={"prompt": "hello"},
        output_data={"completion": "world"},
        duration_ms=12.5,
        metadata={"model": "deepseek"},
    )
    assert step.step_id == "step_1"
    assert step.node_name == "test_node"
    assert step.layer == LayerKind.LAYER_1_PROMPT
    assert step.metadata["model"] == "deepseek"
    assert len(ctx.trajectory) == 1


def test_checkpoint_list_isolation():
    mgr = CheckpointManager()
    ctx = ExecutionContext(session_id="iso_sess")
    mgr.create_checkpoint(ctx, "n1")
    mgr.create_checkpoint(ctx, "n2")

    items = mgr.list_checkpoints()
    assert len(items) == 2
    items.clear()
    assert len(mgr.list_checkpoints()) == 2


def test_schema_validator_root_not_dict():
    with pytest.raises(SchemaValidationError):
        Layer2ContextValidator.validate_schema("not-a-dict", {})


def test_schema_validator_optional_missing_is_fine():
    schema = {"properties": {"optional_str": {"type": "string"}}}
    Layer2ContextValidator.validate_schema({}, schema)


def test_schema_validator_number_accepts_float():
    schema = {"properties": {"score": {"type": "number"}}}
    Layer2ContextValidator.validate_schema({"score": 98.6}, schema)
    Layer2ContextValidator.validate_schema({"score": 100}, schema)
    with pytest.raises(SchemaValidationError):
        Layer2ContextValidator.validate_schema({"score": "98.6"}, schema)


def test_ledger_custom_slots_only():
    ledger = PersistentLedger(allowed_slots=["alpha", "beta"])
    assert "owner" not in ledger.allowed_slots
    assert "alpha" in ledger.allowed_slots
    ledger.update_slot("alpha", "test alpha")
    assert ledger.get_slot("alpha") == "test alpha"


def test_ledger_update_trims_whitespace():
    ledger = PersistentLedger()
    entry = ledger.update_slot("self", "   padded content   \n")
    assert entry.content == "padded content"
    assert ledger.get_slot("self") == "padded content"


def test_state_graph_requires_entry_point():
    graph = StateGraph()
    graph.add_node("lone", lambda c: None)
    ctx = ExecutionContext(session_id="s1")
    with pytest.raises(GraphExecutionError):
        graph.run(ctx)


def test_enums_and_constants():
    assert NodeStatus.PENDING == "PENDING"
    assert NodeStatus.RUNNING == "RUNNING"
    assert LayerKind.LAYER_1_PROMPT == "PROMPT"
    assert LayerKind.LAYER_5_GRAPH == "GRAPH"
