# AutoCetacean v0.3.0 Verification Record

## 1. Deliverables & Files
- `src/autocetacean/workspace.py`: `WorkspaceTransaction`, `SubprocessToolGuard`, `GuardOutcome`, `WorkspaceGuardError`
- `src/autocetacean/mcp_proxy.py`: `MCPStdioRecorder`, `MCPStdioReplayer`, `MCPTraceEntry`, `MCPReplayMismatchError`
- `src/autocetacean/cli.py`: `guard`, `mcp-record`, `mcp-replay` subcommands
- `src/autocetacean/__init__.py`, `pyproject.toml`: version bumped to `0.3.0` and exports added
- `examples/real_agent_guard_and_mcp_replay.py`: end-to-end workspace rollback + MCP stdio record/replay showcase
- `tests/test_workspace_guard.py`, `tests/test_mcp_proxy.py`: new test suites
- `dist/autocetacean-0.3.0-py3-none-any.whl`, `dist/autocetacean-0.3.0.tar.gz`

## 2. Full Test Suite (`pytest -v`)
```text
============================= test session starts ==============================
platform linux -- Python 3.11.2, pytest-9.2.0, pluggy-1.7.0 -- /home/fish/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/fish/projects/autocetacean
configfile: pyproject.toml
testpaths: tests
plugins: platformdirs-4.14.5, asyncio-1.4.1.post1, lazy-fixtures-1.4.1, mock-3.17.0, anyio-4.16.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 92 items

tests/test_checkpoint.py::test_checkpoint_creation_and_deepcopy PASSED   [  1%]
tests/test_checkpoint.py::test_checkpoint_restore PASSED                 [  2%]
tests/test_checkpoint.py::test_checkpoint_eviction PASSED                [  3%]
tests/test_checkpoint.py::test_checkpoint_persistence PASSED             [  4%]
tests/test_cli.py::test_cli_help PASSED                                  [  5%]
tests/test_cli.py::test_cli_ledger_missing_file PASSED                   [  6%]
tests/test_cli.py::test_cli_ledger_human_output PASSED                   [  7%]
tests/test_cli.py::test_cli_ledger_json_output PASSED                    [  8%]
tests/test_extended_coverage.py::test_state_machine_counter_loop PASSED  [  9%]
tests/test_extended_coverage.py::test_execution_context_record_step PASSED [ 10%]
tests/test_extended_coverage.py::test_checkpoint_list_isolation PASSED   [ 11%]
tests/test_extended_coverage.py::test_schema_validator_root_not_dict PASSED [ 13%]
tests/test_extended_coverage.py::test_schema_validator_optional_missing_is_fine PASSED [ 14%]
tests/test_extended_coverage.py::test_schema_validator_number_accepts_float PASSED [ 15%]
tests/test_extended_coverage.py::test_ledger_custom_slots_only PASSED    [ 16%]
tests/test_extended_coverage.py::test_ledger_update_trims_whitespace PASSED [ 17%]
tests/test_extended_coverage.py::test_state_graph_requires_entry_point PASSED [ 18%]
tests/test_extended_coverage.py::test_enums_and_constants PASSED         [ 19%]
tests/test_graph.py::test_linear_graph_execution PASSED                  [ 20%]
tests/test_graph.py::test_conditional_routing_edge PASSED                [ 21%]
tests/test_graph.py::test_node_schema_validation_rejection PASSED        [ 22%]
tests/test_graph.py::test_gate_suspends_execution PASSED                 [ 23%]
tests/test_graph.py::test_duplicate_node_rejected PASSED                 [ 25%]
tests/test_graph.py::test_route_to_unknown_node_raises PASSED            [ 26%]
tests/test_graph.py::test_max_step_limit_halts PASSED                    [ 27%]
tests/test_layers.py::test_schema_validator_valid_object PASSED          [ 28%]
tests/test_layers.py::test_schema_validator_missing_required PASSED      [ 29%]
tests/test_layers.py::test_schema_validator_type_mismatch PASSED         [ 30%]
tests/test_layers.py::test_schema_validator_boolean_not_int PASSED       [ 31%]
tests/test_layers.py::test_schema_validator_nested_structures PASSED     [ 32%]
tests/test_layers.py::test_token_budget_enforcement PASSED               [ 33%]
tests/test_layers.py::test_harness_sandbox_safe_commands PASSED          [ 34%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[rm -rf /] PASSED [ 35%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[rm -Rf /] PASSED [ 36%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[mkfs.ext4 /dev/sda] PASSED [ 38%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[:(){ :|:& };:] PASSED [ 39%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[cat exploit >/dev/sda] PASSED [ 40%]
tests/test_layers.py::test_harness_sandbox_blocks_catastrophic_payloads[chmod 777 /] PASSED [ 41%]
tests/test_layers.py::test_loop_controller_success PASSED                [ 42%]
tests/test_layers.py::test_loop_controller_retry_then_success PASSED     [ 43%]
tests/test_layers.py::test_loop_controller_exhaustion_raises PASSED      [ 44%]
tests/test_ledger.py::test_ledger_initialization PASSED                  [ 45%]
tests/test_ledger.py::test_ledger_invalid_slot_read PASSED               [ 46%]
tests/test_ledger.py::test_ledger_invalid_slot_write PASSED              [ 47%]
tests/test_ledger.py::test_ledger_update_slot_basic PASSED               [ 48%]
tests/test_ledger.py::test_ledger_quota_exceeded PASSED                  [ 50%]
tests/test_ledger.py::test_ledger_quota_cumulative PASSED                [ 51%]
tests/test_ledger.py::test_ledger_utf8_multibyte_counting PASSED         [ 52%]
tests/test_ledger.py::test_ledger_persistence_roundtrip PASSED           [ 53%]
tests/test_ledger.py::test_ledger_rollback PASSED                        [ 54%]
tests/test_ledger.py::test_ledger_rollback_invalid_target PASSED         [ 55%]
tests/test_ledger.py::test_ledger_export_snapshot PASSED                 [ 56%]
tests/test_mcp_proxy.py::test_mcp_record_and_offline_strict_replay PASSED [ 57%]
tests/test_mcp_proxy.py::test_cli_mcp_record_and_replay_subprocesses PASSED [ 58%]
tests/test_replay.py::test_linear_trace_replay_and_summary PASSED        [ 59%]
tests/test_replay.py::test_self_healing_trace_renders_retry_rollback_and_checkpoint PASSED [ 60%]
tests/test_replay.py::test_json_and_jsonl_loading PASSED                 [ 61%]
tests/test_replay.py::test_context_loading PASSED                        [ 63%]
tests/test_replay.py::test_html_export_is_standalone PASSED              [ 64%]
tests/test_replay.py::test_cli_replay_json_plain_html_and_errors PASSED  [ 65%]
tests/test_replay.py::test_empty_and_invalid_files_fail_cleanly PASSED   [ 66%]
tests/test_replay.py::test_invalid_status_is_rejected PASSED             [ 67%]
tests/test_schema_violation.py::test_missing_required_field_records_structured_violation PASSED [ 68%]
tests/test_schema_violation.py::test_type_mismatch_records_expected_and_actual_types PASSED [ 69%]
tests/test_schema_violation.py::test_root_not_object_records_root_violation PASSED [ 70%]
tests/test_schema_violation.py::test_nested_field_path_is_recorded PASSED [ 71%]
tests/test_schema_violation.py::test_graph_failure_records_violation_in_last_trajectory_step PASSED [ 72%]
tests/test_schema_violation.py::test_replay_renders_violation_and_counts_kind PASSED [ 73%]
tests/test_schema_violation.py::test_successful_replay_has_no_violation_output PASSED [ 75%]
tests/test_v02_features.py::test_state_before_after_deepcopy_isolation PASSED [ 76%]
tests/test_v02_features.py::test_step_metadata_carries_checkpoint_id_and_failure_violation PASSED [ 77%]
tests/test_v02_features.py::test_gate_resume_approved_and_conditional_routing PASSED [ 78%]
tests/test_v02_features.py::test_gate_resume_rejected_halts_and_records_audit_step PASSED [ 79%]
tests/test_v02_features.py::test_gate_resume_restore_checkpoint_reverts_corrupted_state PASSED [ 80%]
tests/test_v02_features.py::test_reset_halt_and_run_reset_halt_flag PASSED [ 81%]
tests/test_v02_features.py::test_checkpoint_get_and_load_from_dir_cross_process PASSED [ 82%]
tests/test_v02_features.py::test_export_trace_jsonl_and_json_roundtrip_with_replay_engine PASSED [ 83%]
tests/test_v02_features.py::test_cli_run_with_factory_callable_and_gate_options PASSED [ 84%]
tests/test_v02_features.py::test_cli_graph_with_trace_overlay PASSED     [ 85%]
tests/test_visualizer.py::test_mermaid_linear_graph_marks_entry_finish_and_layers PASSED [ 86%]
tests/test_visualizer.py::test_mermaid_conditional_routes_include_logic_and_retry_cycle PASSED [ 88%]
tests/test_visualizer.py::test_mermaid_gate_uses_hexagon_shape_and_gate_class PASSED [ 89%]
tests/test_visualizer.py::test_html_export_contains_document_structure_and_mermaid_block PASSED [ 90%]
tests/test_visualizer.py::test_cli_graph_prints_mermaid_for_module_target PASSED [ 91%]
tests/test_visualizer.py::test_cli_graph_writes_html_or_mermaid_file PASSED [ 92%]
tests/test_visualizer.py::test_cli_graph_accepts_python_file_target PASSED [ 93%]
tests/test_visualizer.py::test_cli_graph_invalid_target_is_reported PASSED [ 94%]
tests/test_visualizer.py::test_cli_graph_rejects_non_graph_and_missing_target PASSED [ 95%]
tests/test_workspace_guard.py::test_transaction_rollback_restores_all_changes PASSED [ 96%]
tests/test_workspace_guard.py::test_guard_preserves_dirty_git_changes_on_rollback PASSED [ 97%]
tests/test_workspace_guard.py::test_guard_timeout_and_gate_pass PASSED   [ 98%]
tests/test_workspace_guard.py::test_cli_guard_end_to_end PASSED          [100%]

============================== 92 passed in 0.59s ==============================
```

## 3. Isolated Clean Venv Wheel Install & Live Verification
Version: `autocetacean 0.3.0`
`pip install --no-index --find-links=dist autocetacean==0.3.0`:
```text
Looking in links: /home/fish/projects/autocetacean/dist
Processing ./projects/autocetacean/dist/autocetacean-0.3.0-py3-none-any.whl
Installing collected packages: autocetacean
Successfully installed autocetacean-0.3.0
```

`autocetacean guard` rollback test (`rc=1`, restored `m.py`='X=1\n'):
```json
{
  "passed": false,
  "rolled_back": true,
  "timed_out": false,
  "workspace": "/tmp/ac_ws_smoke",
  "cmd": "python3 -c \"open('m.py','w').write('X=0\\n')\"",
  "cmd_returncode": 0,
  "cmd_stdout": "",
  "cmd_stderr": "",
  "gate_cmd": "python3 -c \"import m; assert m.X==1\"",
  "gate_returncode": 1,
  "gate_stdout": "",
  "gate_stderr": "Traceback (most recent call last):\n  File \"<string>\", line 1, in <module>\nAssertionError\n",
  "changes": {
    "added": [],
    "modified": [
      "m.py"
    ],
    "deleted": []
  },
  "duration_ms": 12.53,
  "trace_path": null
}
```

`examples/real_agent_guard_and_mcp_replay.py` in isolated venv (`rc=0`):
```text
[1] Bad edit rolled back: changes={'added': ['junk.txt'], 'modified': ['calc.py'], 'deleted': []}
[2] Good edit committed: changes={'added': [], 'modified': [], 'deleted': []}
[3] Recorded 2 MCP exchanges -> mcp.jsonl
[4] Offline replay ok (id=99 -> 12), strict guard caught drift (id=100 -> -32602)
```
