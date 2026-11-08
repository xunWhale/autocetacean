import pytest

from autocetacean.layers import (
    ContextBudgetExceededError,
    HarnessSecurityError,
    Layer2ContextValidator,
    Layer3HarnessSandbox,
    Layer4LoopController,
    LayerExecutionError,
    SchemaValidationError,
)
from autocetacean.types import ExecutionContext


def test_schema_validator_valid_object():
    schema = {
        "required": ["name", "count"],
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "active": {"type": "boolean"},
        },
    }
    data = {"name": "agent", "count": 10, "active": True}
    Layer2ContextValidator.validate_schema(data, schema)


def test_schema_validator_missing_required():
    schema = {"required": ["title"]}
    with pytest.raises(SchemaValidationError) as exc:
        Layer2ContextValidator.validate_schema({}, schema)
    assert "Missing required schema property" in str(exc.value)


def test_schema_validator_type_mismatch():
    schema = {"properties": {"age": {"type": "integer"}}}
    with pytest.raises(SchemaValidationError):
        Layer2ContextValidator.validate_schema({"age": "not-an-int"}, schema)


def test_schema_validator_boolean_not_int():
    schema = {"properties": {"count": {"type": "integer"}}}
    with pytest.raises(SchemaValidationError):
        Layer2ContextValidator.validate_schema({"count": True}, schema)


def test_schema_validator_nested_structures():
    schema = {
        "properties": {
            "tags": {"type": "array"},
            "config": {"type": "object"},
        }
    }
    Layer2ContextValidator.validate_schema({"tags": ["a", "b"], "config": {"k": "v"}}, schema)
    with pytest.raises(SchemaValidationError):
        Layer2ContextValidator.validate_schema({"tags": "not-a-list"}, schema)


def test_token_budget_enforcement():
    ctx = ExecutionContext(session_id="s1", budget_tokens=100)
    Layer2ContextValidator.enforce_token_budget(ctx, 40)
    assert ctx.used_tokens == 40
    Layer2ContextValidator.enforce_token_budget(ctx, 50)
    assert ctx.used_tokens == 90
    with pytest.raises(ContextBudgetExceededError):
        Layer2ContextValidator.enforce_token_budget(ctx, 20)


def test_harness_sandbox_safe_commands():
    Layer3HarnessSandbox.sanitize_command("ls -la /tmp")
    Layer3HarnessSandbox.sanitize_command("git status")
    Layer3HarnessSandbox.sanitize_command("pytest tests/")


@pytest.mark.parametrize(
    "bad_cmd",
    [
        "rm -rf /",
        "rm -Rf /",
        "mkfs.ext4 /dev/sda",
        ":(){ :|:& };:",
        "cat exploit >/dev/sda",
        "chmod 777 /",
    ],
)
def test_harness_sandbox_blocks_catastrophic_payloads(bad_cmd):
    with pytest.raises(HarnessSecurityError):
        Layer3HarnessSandbox.sanitize_command(bad_cmd)


def test_loop_controller_success():
    ctrl = Layer4LoopController(max_retries=3)
    ctx = ExecutionContext(session_id="s1")
    res = ctrl.execute_with_retry(ctx, "op1", lambda c: 42)
    assert res == 42
    assert len(ctx.trajectory) == 1


def test_loop_controller_retry_then_success():
    ctrl = Layer4LoopController(max_retries=3)
    ctx = ExecutionContext(session_id="s1")
    attempts = [0]

    def flaky(c):
        attempts[0] += 1
        if attempts[0] < 2:
            raise ValueError("transient glitch")
        return "recovered"

    res = ctrl.execute_with_retry(ctx, "op_flaky", flaky)
    assert res == "recovered"
    assert len(ctx.trajectory) == 2


def test_loop_controller_exhaustion_raises():
    ctrl = Layer4LoopController(max_retries=2)
    ctx = ExecutionContext(session_id="s1")

    def fatal(c):
        raise RuntimeError("persistent failure")

    with pytest.raises(LayerExecutionError):
        ctrl.execute_with_retry(ctx, "op_fatal", fatal)
    assert len(ctx.trajectory) == 2
