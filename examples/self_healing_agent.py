"""End-to-End Self-Healing Autonomous Agent using AutoCetacean v0.2.0."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional, Union

from autocetacean import (
    CheckpointManager,
    ExecutionContext,
    GraphExecutionError,
    Layer3HarnessSandbox,
    Layer4LoopController,
    LayerKind,
    PersistentLedger,
    ReplayEngine,
    StateGraph,
)


task_schema = {
    "required": ["bug_report", "target_file"],
    "properties": {
        "bug_report": {"type": "string"},
        "target_file": {"type": "string"},
    },
}


def build_graph(checkpoint_dir: Optional[Union[str, Path]] = None) -> StateGraph:
    """Build the self-healing agent StateGraph with Layer 2/3/4/5 & Gate."""
    checkpoint_mgr = CheckpointManager(storage_dir=checkpoint_dir)
    ledger = PersistentLedger(max_bytes=10752)
    ledger.update_slot("self", "Autonomous Code Repair Agent v0.2.0")
    loop_ctrl = Layer4LoopController(max_retries=3)

    def analyze_task(ctx: ExecutionContext):
        ctx.state["hypothesis"] = "Off-by-one boundary index in buffer scanner"
        ctx.variables["attempts"] = 0
        ctx.variables["harness_failures"] = 0
        return "Analysis complete"

    def generate_patch(ctx: ExecutionContext):
        ctx.variables["attempts"] = ctx.variables.get("attempts", 0) + 1
        attempt = ctx.variables["attempts"]
        ctx.state["patch"] = "buffer[len(buffer)] = 0"
        return f"Candidate patch #{attempt} generated"

    def test_harness(ctx: ExecutionContext):
        def verify_operation(inner_ctx: ExecutionContext):
            if inner_ctx.variables.get("harness_failures", 0) > 0:
                inner_ctx.variables["attempts"] = inner_ctx.variables.get("attempts", 0) + 1
                inner_ctx.state["patch"] = "buffer[len(buffer) - 1] = 0"

            patch = inner_ctx.state.get("patch", "")
            Layer3HarnessSandbox.sanitize_command("pytest tests/")
            if "len(buffer)]" in patch:
                inner_ctx.variables["harness_failures"] = inner_ctx.variables.get("harness_failures", 0) + 1
                raise IndexError("Index out of bounds detected by deterministic harness")
            inner_ctx.state["verified"] = True
            return "All harness tests passed"

        return loop_ctrl.execute_with_retry(ctx, "harness_retry", verify_operation)

    def route_after_test(ctx: ExecutionContext):
        return "approval_gate" if ctx.state.get("verified") else "patch"

    def human_approval_gate(ctx: ExecutionContext):
        return None

    def commit_fix(ctx: ExecutionContext):
        ledger.update_slot(
            "threads",
            f"Resolved bug: {ctx.state['target_file']} with {ctx.state['patch']}",
        )
        ctx.state["committed"] = True
        return "Committed"

    g = StateGraph(checkpoint_manager=checkpoint_mgr)
    g.add_node("analyze", analyze_task, layer=LayerKind.LAYER_2_CONTEXT, expected_schema=task_schema)
    g.add_node("patch", generate_patch, layer=LayerKind.LAYER_1_PROMPT)
    g.add_node("harness", test_harness, layer=LayerKind.LAYER_3_HARNESS)
    g.add_node("approval_gate", human_approval_gate, layer=LayerKind.LAYER_5_GRAPH, is_gate=True)
    g.add_node("commit", commit_fix, layer=LayerKind.LAYER_5_GRAPH)

    g.add_edge("analyze", "patch")
    g.add_edge("patch", "harness")
    g.add_conditional_edge("harness", route_after_test)
    g.add_edge("approval_gate", "commit")
    g.set_entry_point("analyze")
    g.add_finish_point("commit")
    return g


# Kept at module scope so ``autocetacean graph examples.self_healing_agent:graph``
# and ``autocetacean run examples.self_healing_agent:graph`` work out of the box.
graph = build_graph()


def main():
    print("=== AutoCetacean v0.2.0 Autonomous Self-Healing Agent Demo ===")

    # 1. Demonstrate Layer 2 schema interception + reset_halt() recovery
    bad_ctx = ExecutionContext(
        session_id="session_schema_check",
        state={"bug_report": "Buffer overflow in protocol scanner"},
    )
    try:
        graph.run(bad_ctx)
    except GraphExecutionError as exc:
        violation = bad_ctx.trajectory[-1].metadata.get("violation")
        print(f"[!] Layer 2 intercepted invalid input: {exc}")
        print(f"    Violation details: {violation}")
        bad_ctx.reset_halt()
        print(f"    After reset_halt(): is_halted={bad_ctx.is_halted}")

    # 2. Full closed-loop run: Layer 2 -> Layer 1 -> Layer 3/4 retry -> Gate suspend -> Resume -> Trace export
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        agent_graph = build_graph(checkpoint_dir=tmp / "checkpoints")
        ctx = ExecutionContext(
            session_id="session_healing_002",
            state={
                "bug_report": "Buffer overflow in protocol scanner",
                "target_file": "src/net/scanner.c",
            },
        )

        agent_graph.run(ctx)
        print(f"\n[*] Paused at gate: _suspended_at={ctx.variables.get('_suspended_at')}")
        print(f"[*] Latest checkpoint: {agent_graph.checkpoints.get_latest().checkpoint_id}")

        agent_graph.resume(ctx, approved=True)
        trace_path = ctx.export_trace(tmp / "trace.jsonl", format="jsonl")
        print(f"[*] Exported trace to: {trace_path}")

        replay = ReplayEngine(trace_path)
        print("\n" + replay.render_terminal("plain"))


if __name__ == "__main__":
    main()
