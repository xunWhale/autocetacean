"""Core type definitions and telemetry models for AutoCetacean."""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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

    def reset_halt(self) -> "ExecutionContext":
        """Clear halt state so the context can resume or retry execution."""
        self.is_halted = False
        self.halt_reason = None
        return self

    @staticmethod
    def _record_to_trace_event(index: int, record: StepRecord) -> Dict[str, Any]:
        metadata = copy.deepcopy(dict(record.metadata or {}))
        state_before = metadata.pop("state_before", copy.deepcopy(record.input_data))
        state_after = metadata.pop("state_after", copy.deepcopy(record.output_data))
        if not isinstance(state_before, dict):
            state_before = {"input": state_before}
        if not isinstance(state_after, dict):
            state_after = {"output": state_after}
        action = metadata.pop("action", "execute")
        status = metadata.pop("status", "HALT" if record.error else "SUCCESS")
        checkpoint_id = metadata.pop("checkpoint_id", None)
        return {
            "step_index": index,
            "timestamp": record.timestamp,
            "node_name": record.node_name,
            "state_before": state_before,
            "state_after": state_after,
            "action": action,
            "status": status,
            "error_message": record.error,
            "checkpoint_id": checkpoint_id,
            "duration_ms": record.duration_ms,
            "metadata": metadata,
        }

    def to_trace_events(self) -> List[Dict[str, Any]]:
        """Serialize trajectory steps into ReplayEngine-compatible event dicts."""
        return [
            self._record_to_trace_event(index, record)
            for index, record in enumerate(self.trajectory, 1)
        ]

    def export_trace(self, path: Union[str, Path], format: str = "jsonl") -> Path:
        """Export execution trajectory as JSONL or JSON compatible with ReplayEngine."""
        fmt = format.lower()
        if fmt not in {"jsonl", "json"}:
            raise ValueError(f"Unsupported trace format: {format!r}. Expected 'jsonl' or 'json'.")

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        events = self.to_trace_events()
        if fmt == "jsonl":
            lines = [json.dumps(event, ensure_ascii=False, default=str) for event in events]
            content = "\n".join(lines) + ("\n" if lines else "")
        else:
            content = json.dumps(events, indent=2, ensure_ascii=False, default=str) + "\n"
        out_path.write_text(content, encoding="utf-8")
        return out_path


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
