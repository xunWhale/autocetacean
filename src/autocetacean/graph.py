"""Deterministic state machine and execution graph engine."""

from __future__ import annotations

import copy
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

    def _resolve_next_node(self, node_name: str, context: ExecutionContext) -> Optional[str]:
        if node_name in self.conditional_edges:
            return self.conditional_edges[node_name](context)
        return self.edges.get(node_name)

    def run(
        self,
        context: ExecutionContext,
        start_node: Optional[str] = None,
        reset_halt: bool = False,
    ) -> ExecutionContext:
        """Execute state machine until terminal state, budget exhaustion, or gate suspension."""
        if reset_halt:
            context.reset_halt()

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
                state_before = copy.deepcopy(context.state)
                context.variables["_suspended_at"] = current_node_name
                state_after = copy.deepcopy(context.state)
                step = context.record_step(
                    node_name=node.name,
                    layer=LayerKind.LAYER_5_GRAPH,
                    input_data=state_before,
                    output_data=None,
                    metadata={
                        "gate_status": "SUSPENDED",
                        "action": "gate",
                        "status": "SUSPENDED",
                        "state_before": copy.deepcopy(state_before),
                        "state_after": state_after,
                    },
                )
                cp = self.checkpoints.create_checkpoint(context, node.name)
                step.metadata["checkpoint_id"] = cp.checkpoint_id
                break

            start_time = time.time()
            state_before = copy.deepcopy(context.state)
            try:
                # Layer 2 pre-execution schema validation
                if node.expected_schema:
                    Layer2ContextValidator.validate_schema(context.state, node.expected_schema)

                output = node.handler(context)
                duration_ms = (time.time() - start_time) * 1000.0
                state_after = copy.deepcopy(context.state)

                step = context.record_step(
                    node_name=node.name,
                    layer=node.layer,
                    input_data=state_before,
                    output_data=copy.deepcopy(output),
                    duration_ms=duration_ms,
                    metadata={
                        "action": "execute",
                        "status": "SUCCESS",
                        "state_before": copy.deepcopy(state_before),
                        "state_after": state_after,
                    },
                )

                # Persist rolling checkpoint after successful execution
                cp = self.checkpoints.create_checkpoint(context, node.name)
                step.metadata["checkpoint_id"] = cp.checkpoint_id

            except Exception as exc:
                duration_ms = (time.time() - start_time) * 1000.0
                state_after = copy.deepcopy(context.state)
                metadata: Dict[str, Any] = {
                    "action": "execute",
                    "status": "HALT",
                    "state_before": copy.deepcopy(state_before),
                    "state_after": state_after,
                }
                if isinstance(exc, SchemaValidationError):
                    metadata["violation"] = exc.to_violation()
                context.record_step(
                    node_name=node.name,
                    layer=node.layer,
                    input_data=state_before,
                    error=str(exc),
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
                context.is_halted = True
                context.halt_reason = f"Node {node.name!r} failed: {exc}"
                raise GraphExecutionError(f"Error in node {node.name!r}: {exc}") from exc

            # Terminal check
            if current_node_name in self.finish_points:
                break

            # Routing
            next_node = self._resolve_next_node(current_node_name, context)

            if next_node and next_node not in self.nodes:
                raise GraphExecutionError(f"Route to unknown node: {next_node!r}")

            current_node_name = next_node

        return context

    def resume(
        self,
        context: ExecutionContext,
        approved: bool = True,
        restore_checkpoint: bool = False,
    ) -> ExecutionContext:
        """Resume execution from a suspended Gate node or latest checkpoint."""
        restored_cp = None
        if restore_checkpoint:
            latest_cp = self.checkpoints.get_latest()
            if latest_cp is None and self.checkpoints.storage_dir is not None:
                latest_cp = self.checkpoints.load_from_dir()
            if latest_cp is None:
                raise GraphExecutionError("No checkpoint available to restore")
            state_before_rollback = copy.deepcopy(context.state)
            self.checkpoints.restore_into(latest_cp, context)
            state_after_rollback = copy.deepcopy(context.state)
            context.record_step(
                node_name=latest_cp.node_name,
                layer=LayerKind.LAYER_4_LOOP,
                input_data=state_before_rollback,
                output_data={"restored_checkpoint": latest_cp.checkpoint_id},
                metadata={
                    "action": "rollback",
                    "status": "ROLLBACK",
                    "checkpoint_id": latest_cp.checkpoint_id,
                    "state_before": copy.deepcopy(state_before_rollback),
                    "state_after": state_after_rollback,
                },
            )
            restored_cp = latest_cp

        suspended_node = context.variables.get("_suspended_at")
        if suspended_node is not None:
            if suspended_node not in self.nodes:
                raise GraphExecutionError(f"Suspended node not found in graph: {suspended_node!r}")

            if not approved:
                state_snapshot = copy.deepcopy(context.state)
                context.is_halted = True
                context.halt_reason = "Gate rejected"
                context.record_step(
                    node_name=suspended_node,
                    layer=LayerKind.LAYER_5_GRAPH,
                    input_data=state_snapshot,
                    output_data=None,
                    error="Gate rejected",
                    metadata={
                        "gate_status": "REJECTED",
                        "action": "gate",
                        "status": "HALT",
                        "state_before": copy.deepcopy(state_snapshot),
                        "state_after": copy.deepcopy(state_snapshot),
                    },
                )
                return context

            context.variables.pop("_suspended_at", None)
            if suspended_node in self.finish_points:
                context.reset_halt()
                return context

            next_node = self._resolve_next_node(suspended_node, context)
            if next_node is None:
                context.reset_halt()
                return context
            if next_node not in self.nodes:
                raise GraphExecutionError(f"Route to unknown node: {next_node!r}")
            return self.run(context, start_node=next_node, reset_halt=True)

        if restored_cp is not None:
            if not approved:
                state_snapshot = copy.deepcopy(context.state)
                context.is_halted = True
                context.halt_reason = "Gate rejected"
                context.record_step(
                    node_name=restored_cp.node_name,
                    layer=LayerKind.LAYER_5_GRAPH,
                    input_data=state_snapshot,
                    output_data=None,
                    error="Gate rejected",
                    metadata={
                        "gate_status": "REJECTED",
                        "action": "gate",
                        "status": "HALT",
                        "state_before": copy.deepcopy(state_snapshot),
                        "state_after": copy.deepcopy(state_snapshot),
                    },
                )
                return context
            if restored_cp.node_name in self.finish_points:
                context.reset_halt()
                return context
            next_node = self._resolve_next_node(restored_cp.node_name, context)
            if next_node is None:
                context.reset_halt()
                return context
            if next_node not in self.nodes:
                raise GraphExecutionError(f"Route to unknown node: {next_node!r}")
            return self.run(context, start_node=next_node, reset_halt=True)

        raise GraphExecutionError("Cannot resume: context is not suspended at a gate")
