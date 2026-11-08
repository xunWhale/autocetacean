"""The Five Deterministic Layers for Autonomous AI Agents."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from autocetacean.types import ExecutionContext, LayerKind


class LayerExecutionError(Exception):
    """Raised when a layer gate assertion or contract fails."""


class SchemaValidationError(LayerExecutionError):
    """Raised when layer 2 schema validation rejects payload."""


class HarnessSecurityError(LayerExecutionError):
    """Raised when layer 3 sandbox detects unsafe command or side-effect."""


class ContextBudgetExceededError(LayerExecutionError):
    """Raised when layer 2 token budget is exceeded."""


class Layer2ContextValidator:
    """Enforces bounded evidence, token budget, and JSON schema structure."""

    @staticmethod
    def validate_schema(data: Any, expected_schema: Dict[str, Any]) -> None:
        """Validate input dictionary against a lightweight standard JSON schema."""
        if not isinstance(data, dict):
            raise SchemaValidationError(f"Expected object/dict, got {type(data).__name__}")

        req_fields: List[str] = expected_schema.get("required", [])
        for field in req_fields:
            if field not in data:
                raise SchemaValidationError(f"Missing required schema property: {field!r}")

        props: Dict[str, Any] = expected_schema.get("properties", {})
        for prop_name, prop_rule in props.items():
            if prop_name not in data:
                continue
            val = data[prop_name]
            expected_type = prop_rule.get("type")
            if expected_type == "string" and not isinstance(val, str):
                raise SchemaValidationError(f"Property {prop_name!r} expected string, got {type(val).__name__}")
            elif expected_type == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
                raise SchemaValidationError(f"Property {prop_name!r} expected integer, got {type(val).__name__}")
            elif expected_type == "number" and not isinstance(val, (int, float)):
                raise SchemaValidationError(f"Property {prop_name!r} expected number, got {type(val).__name__}")
            elif expected_type == "boolean" and not isinstance(val, bool):
                raise SchemaValidationError(f"Property {prop_name!r} expected boolean, got {type(val).__name__}")
            elif expected_type == "array" and not isinstance(val, list):
                raise SchemaValidationError(f"Property {prop_name!r} expected array/list, got {type(val).__name__}")
            elif expected_type == "object" and not isinstance(val, dict):
                raise SchemaValidationError(f"Property {prop_name!r} expected object/dict, got {type(val).__name__}")

    @staticmethod
    def enforce_token_budget(context: ExecutionContext, estimated_tokens: int) -> None:
        """Ensure token consumption does not exceed context budget."""
        if context.used_tokens + estimated_tokens > context.budget_tokens:
            raise ContextBudgetExceededError(
                f"Token budget exceeded: current {context.used_tokens} + requested {estimated_tokens} "
                f"> budget {context.budget_tokens}"
            )
        context.used_tokens += estimated_tokens


class Layer3HarnessSandbox:
    """Deterministic security gate preventing unconstrained side-effects."""

    UNSAFE_PATTERNS = [
        r"\brm\s+-[rR]f\s+/",
        r"\bmkfs\b",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # Fork bomb
        r">/dev/sd[a-z]",
        r"\bchmod\s+777\s+/",
    ]

    @classmethod
    def sanitize_command(cls, command: str) -> None:
        """Inspect command for obvious catastrophic destructive payloads."""
        clean = command.strip()
        for pattern in cls.UNSAFE_PATTERNS:
            if re.search(pattern, clean):
                raise HarnessSecurityError(f"Command blocked by Layer 3 Harness security policy: {pattern!r}")


class Layer4LoopController:
    """Trajectory auditing and error-directed retry state machine."""

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries

    def execute_with_retry(
        self,
        context: ExecutionContext,
        node_name: str,
        operation: Callable[[ExecutionContext], Any],
    ) -> Any:
        attempts = 0
        last_error = None

        while attempts < self.max_retries:
            attempts += 1
            start = time.time()
            try:
                res = operation(context)
                duration = (time.time() - start) * 1000.0
                context.record_step(
                    node_name=node_name,
                    layer=LayerKind.LAYER_4_LOOP,
                    input_data={"attempt": attempts},
                    output_data=res,
                    duration_ms=duration,
                )
                return res
            except Exception as e:
                duration = (time.time() - start) * 1000.0
                last_error = e
                context.record_step(
                    node_name=node_name,
                    layer=LayerKind.LAYER_4_LOOP,
                    input_data={"attempt": attempts},
                    error=str(e),
                    duration_ms=duration,
                )

        raise LayerExecutionError(f"Node {node_name!r} failed after {self.max_retries} attempts: {last_error}") from last_error
