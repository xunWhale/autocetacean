import pytest

from autocetacean import ExecutionContext, Layer2ContextValidator, ReplayEngine, SchemaValidationError, StateGraph
from autocetacean.graph import GraphExecutionError


def test_missing_required_field_records_structured_violation():
    with pytest.raises(SchemaValidationError) as caught:
        Layer2ContextValidator.validate_schema({}, {"required": ["user"]})

    violation = caught.value.to_violation()
    assert violation["kind"] == "missing"
    assert violation["path"] == "user"
    assert violation["expected"] == "any"
    assert violation["actual"] == "null"


def test_type_mismatch_records_expected_and_actual_types():
    with pytest.raises(SchemaValidationError) as caught:
        Layer2ContextValidator.validate_schema(
            {"age": "thirty"}, {"properties": {"age": {"type": "integer"}}}
        )

    violation = caught.value.to_violation()
    assert violation["kind"] == "type_mismatch"
    assert violation["path"] == "age"
    assert violation["expected"] == "integer"
    assert "str" in violation["actual"]


def test_root_not_object_records_root_violation():
    with pytest.raises(SchemaValidationError) as caught:
        Layer2ContextValidator.validate_schema([], {})

    violation = caught.value.to_violation()
    assert violation["kind"] == "root_not_object"
    assert violation["path"] == "$"
    assert violation["actual"] == "list"


def test_nested_field_path_is_recorded():
    schema = {
        "properties": {
            "profile": {
                "type": "object",
                "required": ["age"],
                "properties": {"age": {"type": "integer"}},
            }
        }
    }
    with pytest.raises(SchemaValidationError) as caught:
        Layer2ContextValidator.validate_schema({"profile": {"age": "old"}}, schema)

    violation = caught.value.to_violation()
    assert violation["path"] == "profile.age"
    assert violation["expected"] == "integer"


def test_graph_failure_records_violation_in_last_trajectory_step():
    graph = StateGraph()
    graph.add_node(
        "validate",
        lambda ctx: "never reached",
        expected_schema={"required": ["user"], "properties": {"user": {"type": "string"}}},
    )
    graph.set_entry_point("validate")
    context = ExecutionContext(session_id="schema-error", state={})

    with pytest.raises(GraphExecutionError):
        graph.run(context)

    violation = context.trajectory[-1].metadata["violation"]
    assert set(violation) == {"kind", "path", "expected", "actual", "message"}
    assert violation["kind"] == "missing"
    assert violation["path"] == "user"
    assert context.is_halted is True


def test_replay_renders_violation_and_counts_kind(tmp_path):
    violation = {
        "kind": "type_mismatch",
        "path": "user.age",
        "expected": "integer",
        "actual": "str",
        "message": "Property 'age' expected integer, got str",
    }
    replay = ReplayEngine.from_events(
        [
            {
                "step_index": 1,
                "timestamp": 1,
                "node_name": "validate",
                "state_before": {"user": {"age": "old"}},
                "state_after": {},
                "status": "HALT",
                "error_message": "Property 'age' expected integer, got str",
                "violation": violation,
            }
        ]
    )

    rendered = replay.render_terminal("plain")
    assert "└─" in rendered
    assert "user.age" in rendered
    assert "integer" in rendered and "str" in rendered
    assert replay.export_summary()["violation_kinds"] == {"type_mismatch": 1}

    html_path = tmp_path / "replay.html"
    replay.export_html(html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "Schema violation" in html
    assert "user.age" in html and "type_mismatch" in html


def test_successful_replay_has_no_violation_output():
    replay = ReplayEngine.from_events(
        [
            {
                "step_index": 1,
                "timestamp": 1,
                "node_name": "ok",
                "state_before": {},
                "state_after": {"ok": True},
                "status": "SUCCESS",
            }
        ]
    )

    assert replay.export_summary()["violation_kinds"] == {}
    assert "└─" not in replay.render_terminal("plain")
