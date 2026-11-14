# AutoCetacean v0.2.0 Verification & Release Evidence

## 1. Summary of v0.2.0 Changes

1. **Deep-Copied State Snapshots & Metadata (`src/autocetacean/graph.py`, `src/autocetacean/layers.py`, `src/autocetacean/replay.py`)**
   - `StateGraph.run()` captures `state_before = copy.deepcopy(context.state)` before Layer 2 schema validation and `node.handler(context)`, and `state_after = copy.deepcopy(context.state)` afterwards.
   - `StepRecord.input_data` receives `state_before` without aliasing/mutation from handlers; `StepRecord.metadata` records `state_before`, `state_after`, `status` (`SUCCESS` / `HALT` / `SUSPENDED`), and the generated `checkpoint_id` (while preserving `violation` on `SchemaValidationError`).
   - `ReplayEngine` now supports `SUSPENDED` in `VALID_STATUSES`, terminal ANSI color/marker (`⏸`), HTML styling, and `suspended_count` in `export_summary()`.
   - `Layer4LoopController.execute_with_retry()` records `state_before`, `state_after`, and `RETRY` / `HALT` / `SUCCESS` statuses for seamless replay convergence tracking.

2. **Gate Resume, Halt Reset & Cross-Process Checkpoints (`src/autocetacean/types.py`, `src/autocetacean/graph.py`, `src/autocetacean/checkpoint.py`)**
   - `ExecutionContext.reset_halt()` and `ExecutionContext.export_trace(path, format="jsonl")`.
   - `StateGraph.run(..., reset_halt=False)` and `StateGraph.resume(context, approved=True, restore_checkpoint=False)`.
   - `CheckpointManager.get_checkpoint(checkpoint_id)` and `CheckpointManager.load_from_dir(storage_dir=None)`.

3. **CLI Closed Loop & Topology Overlay (`src/autocetacean/cli.py`, `src/autocetacean/visualizer.py`, `examples/self_healing_agent.py`)**
   - Added `autocetacean run <target>` supporting `StateGraph`, zero-arg factories (`build_graph`), and `(ctx)` callables with `--input`, `--trace-out`, `--checkpoint-dir`, `--approve-gates`, and `--json`.
   - Added `autocetacean graph --trace <trace>` to overlay execution statuses and schema violations onto Mermaid and HTML exports.
   - Updated `examples/self_healing_agent.py`, `pyproject.toml`, `src/autocetacean/__init__.py`, `README.md`, and `progress.md` to `0.2.0`.

---

## 2. Full Unit Test Suite (`pytest -v`)

Command:
```bash
PYTHONPATH=src /home/fish/.venv/bin/pytest -v
```

Output:
```text
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.2.0, pluggy-1.7.0 -- /home/fish/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /home/fish/projects/autocetacean
configfile: pyproject.toml
testpaths: tests
plugins: platformdirs-4.14.5, asyncio-1.4.1.post1, lazy-fixtures-1.4.1, mock-3.17.0, anyio-4.16.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 86 items

tests/test_checkpoint.py::test_checkpoint_creation_and_deepcopy PASSED   [  1%]
tests/test_checkpoint.py::test_checkpoint_restore PASSED                 [  2%]
tests/test_checkpoint.py::test_checkpoint_eviction PASSED                [  3%]
tests/test_checkpoint.py::test_checkpoint_persistence PASSED             [  4%]
tests/test_cli.py::test_cli_help PASSED                                  [  5%]
tests/test_cli.py::test_cli_ledger_missing_file PASSED                   [  6%]
tests/test_cli.py::test_cli_ledger_human_output PASSED                   [  8%]
tests/test_cli.py::test_cli_ledger_json_output PASSED                    [  9%]
tests/test_extended_coverage.py::test_state_machine_counter_loop PASSED  [ 10%]
tests/test_extended_coverage.py::test_execution_context_record_step PASSED [ 11%]
tests/test_extended_coverage.py::test_checkpoint_list_isolation PASSED   [ 12%]
tests/test_extended_coverage.py::test_schema_validator_root_not_dict PASSED [ 13%]
tests/test_extended_coverage.py::test_schema_validator_optional_missing_is_fine PASSED [ 15%]
tests/test_extended_coverage.py::test_schema_validator_number_accepts_float PASSED [ 16%]
tests/test_extended_coverage.py::test_ledger_custom_slots_only PASSED    [ 17%]
tests/test_extended_coverage.py::test_ledger_update_trims_whitespace PASSED [ 18%]
tests/test_extended_coverage.py::test_state_graph_requires_entry_point PASSED [ 19%]
tests/test_extended_coverage.py::test_enums_and_constants PASSED         [ 20%]
tests/test_graph.py::test_linear_graph_execution PASSED                  [ 22%]
tests/test_graph.py::test_conditional_routing_edge PASSED                [ 23%]
tests/test_graph.py::test_node_schema_validation_rejection PASSED        [ 24%]
tests/test_graph.py::test_gate_suspends_execution PASSED                 [ 25%]
tests/test_graph.py::test_duplicate_node_rejected PASSED                 [ 26%]
tests/test_graph.py::test_route_to_unknown_node_raises PASSED            [ 27%]
tests/test_graph.py::test_max_step_limit_halts PASSED                    [ 29%]
tests/test_layers.py::test_schema_validator_valid_object PASSED          [ 30%]
tests/test_layers.py::test_schema_validator_missing_required PASSED      [ 31%]
tests/test_layers.py::test_schema_validator_type_mismatch PASSED         [ 32%]
tests/test_layers.py::test_schema_validator_boolean_not_int PASSED       [ 33%]
tests/test_layers.py::test_schema_validator_nested_structures PASSED     [ 34%]
tests/test_layers.py::test_token_budget_enforcement PASSED               [ 36%]
tests/test_layers.py::test_harness_sandbox_safe_commands PASSED          [ 37%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[rm -rf /] PASSED [ 38%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[rm -Rf /] PASSED [ 39%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[mkfs.ext4 /dev/sda] PASSED [ 40%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[:(){ :|:& };:] PASSED [ 41%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[cat exploit >/dev/sda] PASSED [ 43%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[chmod 777 /] PASSED [ 44%]
tests/test_layers.py::test_loop_controller_success PASSED                [ 45%]
tests/test_layers.py::test_loop_controller_retry_then_success PASSED     [ 46%]
tests/test_layers.py::test_loop_controller_exhaustion_raises PASSED      [ 47%]
tests/test_ledger.py::test_ledger_initialization PASSED                  [ 48%]
tests/test_ledger.py::test_ledger_invalid_slot_read PASSED               [ 50%]
tests/test_ledger.py::test_ledger_invalid_slot_write PASSED              [ 51%]
tests/test_ledger.py::test_ledger_update_slot_basic PASSED               [ 52%]
tests/test_ledger.py::test_ledger_quota_exceeded PASSED                  [ 53%]
tests/test_ledger.py::test_ledger_quota_cumulative PASSED                [ 54%]
tests/test_ledger.py::test_ledger_utf8_multibyte_counting PASSED         [ 55%]
tests/test_ledger.py::test_ledger_persistence_roundtrip PASSED           [ 56%]
tests/test_ledger.py::test_ledger_rollback PASSED                        [ 58%]
tests/test_ledger.py::test_ledger_rollback_invalid_target PASSED         [ 59%]
tests/test_ledger.py::test_ledger_export_snapshot PASSED                 [ 60%]
tests/test_replay.py::test_linear_trace_replay_and_summary PASSED        [ 61%]
tests/test_replay.py::test_self_healing_trace_renders_retry_rollback_and_checkpoint PASSED [ 62%]
tests/test_replay.py::test_json_and_jsonl_loading PASSED                 [ 63%]
tests/test_replay.py::test_context_loading PASSED                        [ 65%]
tests/test_replay.py::test_html_export_is_standalone PASSED              [ 66%]
tests/test_replay.py::test_cli_replay_json_plain_html_and_errors PASSED  [ 67%]
tests/test_replay.py::test_empty_and_invalid_files_fail_cleanly PASSED   [ 68%]
tests/test_replay.py::test_invalid_status_is_rejected PASSED             [ 69%]
tests/test_schema_violation.py::test_missing_required_field_records_structured_violation PASSED [ 70%]
tests/test_schema_violation.py::test_type_mismatch_records_expected_and_actual_types PASSED [ 72%]
tests/test_schema_violation.py::test_root_not_object_records_root_violation PASSED [ 73%]
tests/test_schema_violation.py::test_nested_field_path_is_recorded PASSED [ 74%]
tests/test_schema_violation.py::test_graph_failure_records_violation_in_last_trajectory_step PASSED [ 75%]
tests/test_schema_violation.py::test_replay_renders_violation_and_counts_kind PASSED [ 76%]
tests/test_schema_violation.py::test_successful_replay_has_no_violation_output PASSED [ 77%]
tests/test_v02_features.py::test_state_before_after_deepcopy_isolation PASSED [ 79%]
tests/test_v02_features.py::test_step_metadata_carries_checkpoint_id_and_failure_violation PASSED [ 80%]
tests/test_v02_features.py::test_gate_resume_approved_and_conditional_routing PASSED [ 81%]
tests/test_v02_features.py::test_gate_resume_rejected_halts_and_records_audit_step PASSED [ 82%]
tests/test_v02_features.py::test_gate_resume_restore_checkpoint_reverts_corrupted_state PASSED [ 83%]
tests/test_v02_features.py::test_reset_halt_and_run_reset_halt_flag PASSED [ 84%]
tests/test_v02_features.py::test_checkpoint_get_and_load_from_dir_cross_process PASSED [ 86%]
tests/test_v02_features.py::test_export_trace_jsonl_and_json_roundtrip_with_replay_engine PASSED [ 87%]
tests/test_v02_features.py::test_cli_run_with_factory_callable_and_gate_options PASSED [ 88%]
tests/test_v02_features.py::test_cli_graph_with_trace_overlay PASSED     [ 89%]
tests/test_visualizer.py::test_mermaid_linear_graph_marks_entry_finish_and_layers PASSED [ 90%]
tests/test_visualizer.py::test_mermaid_conditional_routes_include_logic_and_retry_cycle PASSED [ 91%]
tests/test_visualizer.py::test_mermaid_gate_uses_hexagon_shape_and_gate_class PASSED [ 93%]
tests/test_visualizer.py::test_html_export_contains_document_structure_and_mermaid_block PASSED [ 94%]
tests/test_visualizer.py::test_cli_graph_prints_mermaid_for_module_target PASSED [ 95%]
tests/test_visualizer.py::test_cli_graph_writes_html_or_mermaid_file PASSED [ 96%]
tests/test_visualizer.py::test_cli_graph_accepts_python_file_target PASSED [ 97%]
tests/test_visualizer.py::test_cli_graph_invalid_target_is_reported PASSED [ 98%]
tests/test_visualizer.py::test_cli_graph_rejects_non_graph_and_missing_target PASSED [100%]

============================== 86 passed in 0.07s ==============================
```

---

## 3. Isolated Wheel Build & End-to-End CLI Verification (`/tmp/autocetacean_v02_venv`)

Built wheel & source distribution:
- `dist/autocetacean-0.2.0-py3-none-any.whl`
- `dist/autocetacean-0.2.0.tar.gz`

Installed into clean `/tmp/autocetacean_v02_venv` and verified `autocetacean run` -> `autocetacean replay` -> `autocetacean graph --trace`:

```console
$ /tmp/autocetacean_v02_venv/bin/autocetacean --version
autocetacean 0.2.0

$ /tmp/autocetacean_v02_venv/bin/autocetacean run examples/self_healing_agent.py:graph \
  --input '{"bug_report":"Buffer overflow in protocol scanner","target_file":"src/net/scanner.c"}' \
  --checkpoint-dir /tmp/autocetacean_v02_cps \
  --trace-out /tmp/trace_paused.jsonl --json
{
  "session_id": "cli_run",
  "status": "SUSPENDED",
  "is_halted": false,
  "halt_reason": null,
  "suspended_at": "approval_gate",
  "steps": 6,
  "state": {
    "bug_report": "Buffer overflow in protocol scanner",
    "target_file": "src/net/scanner.c",
    "hypothesis": "Off-by-one boundary index in buffer scanner",
    "patch": "buffer[len(buffer) - 1] = 0",
    "verified": true
  },
  "trace_out": "/tmp/trace_paused.jsonl",
  "latest_checkpoint_id": "cp_cli_run_6_1794615035101",
  "error": null
}

$ /tmp/autocetacean_v02_venv/bin/autocetacean run examples/self_healing_agent.py:graph \
  --input '{"bug_report":"Buffer overflow in protocol scanner","target_file":"src/net/scanner.c"}' \
  --checkpoint-dir /tmp/autocetacean_v02_cps \
  --approve-gates --trace-out /tmp/trace.jsonl --json
{
  "session_id": "cli_run",
  "status": "COMPLETED",
  "is_halted": false,
  "halt_reason": null,
  "suspended_at": null,
  "steps": 7,
  "state": {
    "bug_report": "Buffer overflow in protocol scanner",
    "target_file": "src/net/scanner.c",
    "hypothesis": "Off-by-one boundary index in buffer scanner",
    "patch": "buffer[len(buffer) - 1] = 0",
    "verified": true,
    "committed": true
  },
  "trace_out": "/tmp/trace.jsonl",
  "latest_checkpoint_id": "cp_cli_run_7_1794615035128",
  "error": null
}

$ /tmp/autocetacean_v02_venv/bin/autocetacean replay /tmp/trace.jsonl --plain
AutoCetacean Execution Replay
===============================
✓ [  1] analyze -- execute [SUCCESS]  checkpoint=cp_cli_run_1_1794615035128  diff=hypothesis
  │
✓ [  2] patch -- execute [SUCCESS]  checkpoint=cp_cli_run_2_1794615035128  diff=patch
  │
↻ [  3] harness_retry -- retry [RETRY]  error=Index out of bounds detected by deterministic harness
  │
✓ [  4] harness_retry -- retry [SUCCESS]  diff=patch,verified
  │
✓ [  5] harness -- execute [SUCCESS]  checkpoint=cp_cli_run_5_1794615035128  diff=patch,verified
  │
⏸ [  6] approval_gate -- gate [SUSPENDED]  checkpoint=cp_cli_run_6_1794615035128
  │
✓ [  7] commit -- execute [SUCCESS]  checkpoint=cp_cli_run_7_1794615035128  diff=committed

Steps: 7  Success: 5  Rollbacks: 0  Convergence: 100.0%

$ /tmp/autocetacean_v02_venv/bin/autocetacean replay /tmp/trace.jsonl --json
{
  "total_steps": 7,
  "successful_steps": 5,
  "retry_count": 1,
  "rollback_count": 0,
  "halt_count": 0,
  "suspended_count": 1,
  "duration_ms": 0.522,
  "duration_seconds": 0.001,
  "self_healing_convergence_rate": 1.0,
  "incident_count": 1,
  "violation_kinds": {}
}

$ /tmp/autocetacean_v02_venv/bin/autocetacean graph examples/self_healing_agent.py:graph --trace /tmp/trace.jsonl
flowchart TD
    node_1["analyze [CONTEXT; ENTRY / SUCCESS x1]"]
    node_2["patch [PROMPT; SUCCESS x1]"]
    node_3["harness [HARNESS; SUCCESS x1]"]
    node_4{{"approval_gate [GRAPH; SUSPENDED x1]"}}
    node_5["commit [GRAPH; FINISH / SUCCESS x1]"]
    node_1 --> node_2
    node_2 --> node_3
    node_4 --> node_5
    node_3 -.->|else| node_2
    node_3 -.->|if ctx.state.get verified| node_4
    classDef entry fill:#123d5a,stroke:#67d6ff,color:#f2fbff,stroke-width:2px
    classDef finish fill:#123f3a,stroke:#5ee6b4,color:#f2fff9,stroke-width:2px
    classDef gate fill:#5b4315,stroke:#ffd166,color:#fff8de,stroke-width:2px
    classDef layer fill:#102539,stroke:#3d6a88,color:#d9edf8
    classDef trace_success fill:#123f3a,stroke:#36c275,color:#e9fff4,stroke-width:2px
    classDef trace_retry fill:#4a3b12,stroke:#e4ad36,color:#fff6dc,stroke-width:2px
    classDef trace_rollback fill:#3a2356,stroke:#b982ed,color:#f5ebff,stroke-width:2px
    classDef trace_halt fill:#541c24,stroke:#f06464,color:#ffe9ec,stroke-width:2px
    classDef trace_suspended fill:#13425c,stroke:#4cc9f0,color:#e6f9ff,stroke-width:2px
    class node_1 entry
    class node_5 finish
    class node_4 gate
    class node_1,node_2,node_3,node_5 trace_success
    class node_4 trace_suspended
```

Schema violation failure path in isolated venv:
```console
$ /tmp/autocetacean_v02_venv/bin/autocetacean run examples/self_healing_agent.py:graph \
  --input '{"bug_report":"Buffer overflow in protocol scanner"}' \
  --trace-out /tmp/trace_err.jsonl; echo "EXIT_CODE=$?"
AutoCetacean Run [FAILED] session=cli_run steps=1
Trace exported: /tmp/trace_err.jsonl
autocetacean: execution failed: Error in node 'analyze': Missing required schema property: 'target_file'
EXIT_CODE=1

$ /tmp/autocetacean_v02_venv/bin/autocetacean replay /tmp/trace_err.jsonl --plain
AutoCetacean Execution Replay
===============================
✗ [  1] analyze -- execute [HALT]  error=Missing required schema property: 'target_file'
    └─ 字段 target_file：期望 string，实际 null（missing）

Steps: 1  Success: 0  Rollbacks: 0  Convergence: 0.0%

$ /tmp/autocetacean_v02_venv/bin/autocetacean graph examples/self_healing_agent.py:graph --trace /tmp/trace_err.jsonl
flowchart TD
    node_1["analyze [CONTEXT; ENTRY / HALT x1 / violation missing target_file]"]
    node_2["patch [PROMPT]"]
    node_3["harness [HARNESS]"]
    node_4{{"approval_gate [GRAPH]"}}
    node_5["commit [GRAPH; FINISH]"]
    ...
    class node_1 trace_halt
```

Temporary `/tmp/autocetacean_v02_venv`, `/tmp/autocetacean_v02_cps`, and `/tmp/trace*.jsonl` artifacts were removed after verification.
