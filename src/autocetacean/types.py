"""Core type definitions and telemetry models for AutoCetacean."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union


class NodeStatus(str, Enum):
    """Execution status of an individual graph node."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    SUSPENDED = "SUSPENDED"  # Waiting on human gate or async approval


class LayerKind(str, Enum):
    """The five layers of deterministic agent engineering."""
    LAYER_1_PROMPT = "PROMPT"      # Stochastic hypothesis generation
    LAYER_2_CONTEXT = "CONTEXT"    # Bounded evidence & schema validation
    LAYER_3_HARNESS = "HARNESS"    # Sandbox isolation & deterministic assertions
    LAYER_4_LOOP = "LOOP"          # Audited trajectory & self-healing retry
    LAYER_5_GRAPH = "GRAPH"        # State machine flow & conditional routing


@dataclass
class StepRecord:
    """Audit log of a single atomic execution step."""
    step_id: str
    node_name: str
    layer: LayerKind
    input_data: Any
    output_data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    """Stateful context passed across the agent graph."""
    session_id: str
    state: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    trajectory: List[StepRecord] = field(default_factory=list)
    budget_tokens: int = 100_000
    used_tokens: int = 0
    max_steps: int = 50
    is_halted: bool = False
    halt_reason: Optional[str] = None

    def record_step(
        self,
        node_name: str,
        layer: LayerKind,
        input_data: Any,
        output_data: Any = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StepRecord:
        record = StepRecord(
            step_id=f"step_{len(self.trajectory) + 1}",
            node_name=node_name,
            layer=layer,
            input_data=input_data,
            output_data=output_data,
            error=error,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self.trajectory.append(record)
        return record


@dataclass
class Checkpoint:
    """A serialized snapshot of the execution state."""
    checkpoint_id: str
    session_id: str
    step_index: int
    node_name: str
    state: Dict[str, Any]
    variables: Dict[str, Any]
    used_tokens: int
    timestamp: float = field(default_factory=time.time)
    schema_version: str = "1.0.0"
