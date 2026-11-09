"""End-to-End Self-Healing Autonomous Agent using AutoCetacean."""

from __future__ import annotations

from autocetacean import (
    CheckpointManager,
    ExecutionContext,
    LayerKind,
    PersistentLedger,
    StateGraph,
)


def main():
    print("=== AutoCetacean Autonomous Self-Healing Agent Demo ===")

    checkpoint_mgr = CheckpointManager()
    ledger = PersistentLedger(max_bytes=10752)
    ledger.update_slot("self", "Autonomous Code Repair Agent v1.0")

    graph = StateGraph(checkpoint_manager=checkpoint_mgr)

    task_schema = {
        "required": ["bug_report", "target_file"],
        "properties": {
            "bug_report": {"type": "string"},
            "target_file": {"type": "string"},
        },
    }

    def analyze_task(ctx: ExecutionContext):
        print(f"[*] Analyzing task: {ctx.state['bug_report']}")
        ctx.state["hypothesis"] = "Off-by-one boundary index in buffer scanner"
        ctx.variables["attempts"] = 0
        return "Analysis complete"

    def generate_patch(ctx: ExecutionContext):
        ctx.variables["attempts"] = ctx.variables.get("attempts", 0) + 1
        attempt = ctx.variables["attempts"]
        print(f"[*] Generating patch attempt #{attempt}...")
        if attempt == 1:
            ctx.state["patch"] = "buffer[len(buffer)] = 0"
        else:
            ctx.state["patch"] = "buffer[len(buffer) - 1] = 0"
        return f"Patch #{attempt} generated"

    def test_harness(ctx: ExecutionContext):
        patch = ctx.state.get("patch", "")
        print(f"[*] Harness testing patch: {patch!r}")
        if "len(buffer)]" in patch:
            raise IndexError("Index out of bounds detected by deterministic harness")
        ctx.state["verified"] = True
        return "All harness tests passed"

    def handle_recovery(ctx: ExecutionContext):
        print("[!] Harness detected regression! Rolling back to last verified checkpoint...")
        latest_cp = checkpoint_mgr.get_latest()
        if latest_cp:
            checkpoint_mgr.restore_into(latest_cp, ctx)
            print(f"[+] Restored state from checkpoint: {latest_cp.checkpoint_id} (node: {latest_cp.node_name})")
        return "Recovery complete"

    def route_after_test(ctx: ExecutionContext):
        if ctx.state.get("verified"):
            return "commit"
        return "retry"

    def commit_fix(ctx: ExecutionContext):
        print("[*] Committing verified patch into ledger...")
        ledger.update_slot("threads", f"Resolved bug: {ctx.state['target_file']} with {ctx.state['patch']}")
        return "Committed"

    graph.add_node("analyze", analyze_task, layer=LayerKind.LAYER_2_CONTEXT, expected_schema=task_schema)
    graph.add_node("patch", generate_patch, layer=LayerKind.LAYER_1_PROMPT)
    graph.add_node("harness", test_harness, layer=LayerKind.LAYER_3_HARNESS)
    graph.add_node("recover", handle_recovery, layer=LayerKind.LAYER_4_LOOP)
    graph.add_node("commit", commit_fix, layer=LayerKind.LAYER_5_GRAPH)

    graph.add_edge("analyze", "patch")
    graph.add_edge("patch", "harness")
    graph.add_conditional_edge("harness", route_after_test)
    graph.add_edge("recover", "patch")

    graph.set_entry_point("analyze")
    graph.add_finish_point("commit")

    ctx = ExecutionContext(
        session_id="session_healing_001",
        state={
            "bug_report": "Buffer overflow in protocol scanner",
            "target_file": "src/net/scanner.c",
        },
    )

    try:
        graph.run(ctx)
    except Exception as e:
        print(f"[*] Intercepted expected harness failure: {e}")
        ctx.is_halted = False
        ctx.halt_reason = None
        graph.run(ctx, start_node="recover")

    print("\n=== Execution Summary ===")
    print(f"Status: Verified = {ctx.state.get('verified')}")
    print(f"Total Trajectory Steps: {len(ctx.trajectory)}")
    for step in ctx.trajectory:
        status = "FAIL" if step.error else "PASS"
        print(f"  [{status}] Step {step.step_id:6s} | Layer: {step.layer.value:8s} | Node: {step.node_name:8s} | {step.output_data or step.error}")

    print(f"\nFinal Memory Ledger Revision: {ledger.revision}")
    print(f"Final Memory Threads Slot:\n{ledger.get_slot('threads')}")


if __name__ == "__main__":
    main()
