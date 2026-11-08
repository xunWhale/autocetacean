"""Deterministic state machine and execution graph engine."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from autocetacean.checkpoint import CheckpointManager
from autocetacean.layers import (
    Layer2ContextValidator,
    Layer3HarnessSandbox,
    LayerExecutionError,
    SchemaValidationError,
)
from autocetacean.types import ExecutionContext, LayerKind, NodeStatus


class GraphExecutionError(Exception):
    """Raised on graph structural errors or unhandled node failures."""


class GraphNode:
    """An executable node inside the state machine."""

    def __init__(
        self,
        name: str,
        handler: Callable[[ExecutionContext], Any],
        layer: LayerKind = LayerKind.LAYER_5_GRAPH,
        expected_schema: Optional[Dict[str, Any]] = None,
        is_gate: bool = False,
    ) -> None:
        self.name = name
        self.handler = handler
        self.layer = layer
        self.expected_schema = expected_schema
        self.is_gate = is_gate


class StateGraph:
    """Explicit conditional DAG / Cyclic State Machine for Agents."""

    def __init__(self, checkpoint_manager: Optional[CheckpointManager] = None) -> None:
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, str] = {}
        self.conditional_edges: Dict[str, Callable[[ExecutionContext], str]] = {}
        self.entry_point: Optional[str] = None
        self.finish_points: Set[str] = set()
        self.checkpoints = checkpoint_manager or CheckpointManager()

    def add_node(
        self,
        name: str,
        handler: Callable[[ExecutionContext], Any],
        layer: LayerKind = LayerKind.LAYER_5_GRAPH,
        expected_schema: Optional[Dict[str, Any]] = None,
        is_gate: bool = False,
    ) -> StateGraph:
        if name in self.nodes:
            raise GraphExecutionError(f"Duplicate node registration: {name!r}")
        self.nodes[name] = GraphNode(
            name=name,
            handler=handler,
            layer=layer,
            expected_schema=expected_schema,
            is_gate=is_gate,
        )
        return self

    def add_edge(self, from_node: str, to_node: str) -> StateGraph:
        self.edges[from_node] = to_node
        return self

    def add_conditional_edge(
        self,
        from_node: str,
        router: Callable[[ExecutionContext], str],
    ) -> StateGraph:
        self.conditional_edges[from_node] = router
        return self

    def set_entry_point(self, name: str) -> StateGraph:
        self.entry_point = name
        return self

    def add_finish_point(self, name: str) -> StateGraph:
        self.finish_points.add(name)
        return self

    def run(self, context: ExecutionContext, start_node: Optional[str] = None) -> ExecutionContext:
        """Execute state machine until terminal state, budget exhaustion, or gate suspension."""
        current_node_name = start_node or self.entry_point
        if not current_node_name or current_node_name not in self.nodes:
            raise GraphExecutionError(f"Invalid entry node: {current_node_name!r}")

        while current_node_name and not context.is_halted:
            if len(context.trajectory) >= context.max_steps:
                context.is_halted = True
                context.halt_reason = f"Max step limit reached ({context.max_steps})"
                break

            node = self.nodes[current_node_name]

            # Gate node: human or external approval required
            if node.is_gate:
                context.variables["_suspended_at"] = current_node_name
                context.record_step(
                    node_name=node.name,
                    layer=LayerKind.LAYER_5_GRAPH,
                    input_data=dict(context.state),
                    output_data=None,
                    metadata={"gate_status": "SUSPENDED"},
                )
                self.checkpoints.create_checkpoint(context, node.name)
                break

            start_time = time.time()
            try:
                # Layer 2 pre-execution schema validation
                if node.expected_schema:
                    Layer2ContextValidator.validate_schema(context.state, node.expected_schema)

                output = node.handler(context)
                duration_ms = (time.time() - start_time) * 1000.0

                context.record_step(
                    node_name=node.name,
                    layer=node.layer,
                    input_data=dict(context.state),
                    output_data=output,
                    duration_ms=duration_ms,
                )

                # Persist rolling checkpoint after successful execution
                self.checkpoints.create_checkpoint(context, node.name)

            except Exception as exc:
                duration_ms = (time.time() - start_time) * 1000.0
                context.record_step(
                    node_name=node.name,
                    layer=node.layer,
                    input_data=dict(context.state),
                    error=str(exc),
                    duration_ms=duration_ms,
                )
                context.is_halted = True
                context.halt_reason = f"Node {node.name!r} failed: {exc}"
                raise GraphExecutionError(f"Error in node {node.name!r}: {exc}") from exc

            # Terminal check
            if current_node_name in self.finish_points:
                break

            # Routing
            if current_node_name in self.conditional_edges:
                next_node = self.conditional_edges[current_node_name](context)
            else:
                next_node = self.edges.get(current_node_name)

            if next_node and next_node not in self.nodes:
                raise GraphExecutionError(f"Route to unknown node: {next_node!r}")

            current_node_name = next_node

        return context
