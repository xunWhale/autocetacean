# AutoCetacean

[![CI](https://github.com/xunWhale/autocetacean/actions/workflows/ci.yml/badge.svg)](https://github.com/xunWhale/autocetacean/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero-Dependencies](https://img.shields.io/badge/Dependencies-0_Runtime-success.svg)](pyproject.toml)

**Your coding agent just broke your repo. Get it back with one command.**

```bash
pip install "autocetacean @ git+https://github.com/xunWhale/autocetacean"
autocetacean guard --workspace . --cmd "claude -p 'fix the failing test'" --gate "pytest -q"
```

If the gate fails, the guard restores the workspace to what it was — atomically, no `git stash`, no manual diff review. That includes the files `git status` never sees.

**Verified, verbatim** (throwaway repo; the "agent" modified a tracked file, deleted an untracked file, removed a directory, and created a new one):

```text
$ autocetacean guard --workspace . --cmd "printf 'VALUE=999\n' > a.py; rm untracked.txt; echo junk > junk.log; rm -rf sub" \
      --gate "python3 -c 'import a; assert a.VALUE==1'"
AutoCetacean Guard [ROLLED_BACK] cmd_rc=0 gate_rc=1 rolled_back=True

$ cat a.py             # VALUE = 1  — restored
$ cat untracked.txt    # keep me   — restored, even though git never tracked it
$ cat sub/b.py         # nested    — directory restored
$ ls junk.log          # gone      — created by the agent, deleted by the rollback
```

That is the whole idea: an agent's edits are a transaction, and a deterministic gate decides whether to commit or roll back.

Curious why `git checkout` does not cover this? Run [`examples/git-is-not-enough.sh`](examples/git-is-not-enough.sh) — it reproduces the exact case where git loses an untracked file an agent deleted, and the guard gets it back. The reasoning is in [Why not just git?](docs/why-not-just-git.md). Already lost files? [Claude Code deleted my files](docs/claude-code-deleted-my-files.md) goes through what each recovery path can actually reach, and what none of them can.

---

**The Deterministic Runtime, State-Machine Execution Graph, and Rolling Checkpoint Engine for Autonomous AI Agents.**

> *"Modern agent engineering is not about praying to bigger models — it is about engineering deterministic constraints."*

---

---

## See it work in 60 seconds

```bash
pip install "autocetacean @ git+https://github.com/xunWhale/autocetacean"
autocetacean demo
```

`autocetacean demo` needs no API key, no network, and no third-party package. It creates a throwaway
project in a temp directory and proves two things end to end:

1. **Transactional workspace rollback.** An "agent" writes broken code; a `unittest` gate rejects it;
   the guard restores every modified file and deletes what the agent created — atomically.
2. **Offline MCP replay.** A real stdio MCP server session is recorded to JSONL, then replayed with
   the backend process gone. Matching calls return the recorded result; a drifted call is rejected
   with JSON-RPC `-32602` in strict mode.

A successful run ends with:

```text
AutoCetacean demo: ALL CHECKS PASSED (guard rollback + mcp replay)
```

---

## Why AutoCetacean?

Most contemporary agent frameworks treat language models as black-box loops: they append endlessly to a prompt, hope the model parses tool arguments correctly, and pray it recovers when an error occurs. In practice:
- Long runs drown in conversational noise and token budget exhaustion.
- Malformed tool arguments crash the runner at runtime.
- Transient errors send the agent into hallucination death-spirals.

AutoCetacean wraps stochastic completions inside a **five-layer deterministic architecture** ([RFC-001](docs/RFC-001-FIVE-LAYER-RUNTIME.md)):

1. **Layer 1 (Prompt)**: Untrusted hypothesis generation.
2. **Layer 2 (Context)**: Hard token budgets and strict JSON Schema validation before dispatch.
3. **Layer 3 (Harness)**: Deterministic execution sandbox with safety policies.
4. **Layer 4 (Loop)**: Step-by-step trajectory auditing and error-directed retry.
5. **Layer 5 (Graph)**: Resilient state machine with conditional routing and human approval gates.

Along with:
- **Rolling Checkpoints**: Snapshot state at every node boundary, enabling deterministic step-by-step replay and context compaction.
- **Persistent Structured Ledger**: Multi-slot versioned memory with strict byte quotas and atomic rollback.
- **Zero Third-Party Runtime Dependencies**: Built entirely on standard Python 3.10+ primitives (`asyncio`, `json`, `dataclasses`, `pathlib`).

## Quickstart

### Installation

```bash
pip install "autocetacean @ git+https://github.com/xunWhale/autocetacean"
```

### 1. Build a Deterministic State Graph

```python
from autocetacean import StateGraph, ExecutionContext, LayerKind

graph = StateGraph()

# Add a node with strict Layer 2 schema validation
schema = {
    "required": ["query"],
    "properties": {"query": {"type": "string"}}
}

def retrieve_docs(ctx: ExecutionContext):
    ctx.state["docs"] = [f"Result for {ctx.state['query']}"]
    return "ok"

def format_answer(ctx: ExecutionContext):
    ctx.state["answer"] = f"Synthesized from {len(ctx.state['docs'])} docs"
    return "ok"

graph.add_node("retrieve", retrieve_docs, layer=LayerKind.LAYER_2_CONTEXT, expected_schema=schema)
graph.add_node("answer", format_answer, layer=LayerKind.LAYER_1_PROMPT)
graph.add_edge("retrieve", "answer")
graph.set_entry_point("retrieve")
graph.add_finish_point("answer")

ctx = ExecutionContext(session_id="run_1", state={"query": "MCP architecture"})
graph.run(ctx)

print(ctx.state["answer"])
# -> "Synthesized from 1 docs"
print(f"Executed {len(ctx.trajectory)} audited steps.")
```

### 2. Versioned Persistent Memory Ledger

```python
from autocetacean import PersistentLedger

# Enforces global 10.5 KB memory ceiling and atomic slot commits
ledger = PersistentLedger("memory.json", max_bytes=10752)

entry = ledger.update_slot("owner", "Preferred tone: concise, direct, technical")
print(f"Revision: {entry.revision}, Bytes: {entry.byte_size}")

# Atomic rollback if an agent hallucinated bad memory
ledger.rollback_to(entry.revision - 1)
```

### 3. Run a StateGraph from the CLI

`autocetacean run` executes a `StateGraph` instance, a `build_graph()` factory, or a `(ctx)` callable from a Python module or file, optionally persisting rolling checkpoints, auto-approving human gates, and exporting a JSONL execution trace.

```bash
# Execute the self-healing agent demo with auto-approved Gate and trace export
PYTHONPATH=src autocetacean run examples.self_healing_agent:graph \
  --input '{"bug_report":"Buffer overflow in protocol scanner","target_file":"src/net/scanner.c"}' \
  --checkpoint-dir .checkpoints \
  --approve-gates \
  --trace-out execution-trace.jsonl

# Pause at a Gate node (inspect state / checkpoint before resuming in Python via graph.resume)
PYTHONPATH=src autocetacean run examples.self_healing_agent:build_graph \
  --input @task_input.json \
  --trace-out suspended-trace.jsonl \
  --json
```

In Python, `ExecutionContext.reset_halt()`, `ExecutionContext.export_trace()`, `StateGraph.resume(ctx, approved=..., restore_checkpoint=...)`, `StateGraph.run(..., reset_halt=True)`, and `CheckpointManager.get_checkpoint()` / `load_from_dir()` provide full programmatic recovery across gates and process restarts.

### 4. Replay an Execution Trace

`autocetacean replay` accepts either a JSON array/object or one JSON event per line. Each event can include `step_index`, `timestamp`, `node_name`, `state_before`, `state_after`, `action`, `status`, `error_message`, and `checkpoint_id`.

```bash
# Read a human-friendly state transition timeline
autocetacean replay execution-trace.jsonl

# Disable ANSI colors for CI logs
autocetacean replay execution-trace.jsonl --plain

# Export summary JSON and a standalone HTML timeline
autocetacean replay execution-trace.jsonl --json --html replay.html
```

The terminal and HTML views highlight retries, checkpoint rollbacks, suspended gates, halts, and state diffs. Schema validation failures also show the violating field path, expected type, actual type, and violation kind when replaying a trace. The JSON summary includes step counts, elapsed time, rollback count, suspended count, the self-healing convergence rate, and `violation_kinds` counts.

### 5. Export and visualize a StateGraph topology

`autocetacean graph` loads a `StateGraph` from a Python module or file and exports its static topology (optionally overlaid with an execution trace via `--trace`). The target uses `module_path:graph_var` syntax; file targets use `path/to/workflow.py:graph_var`.

```bash
# Print Mermaid source to the terminal
PYTHONPATH=src autocetacean graph examples.self_healing_agent:graph

# Overlay an execution trace onto the Mermaid or HTML topology
PYTHONPATH=src autocetacean graph examples.self_healing_agent:graph \
  --trace execution-trace.jsonl --format html --output workflow-traced.html

# Write Mermaid source to a file
PYTHONPATH=src autocetacean graph examples.self_healing_agent:graph \
  --format mermaid --output workflow.mmd

# Write a standalone HTML viewer with deep-ocean styling and a zoomable graph area
PYTHONPATH=src autocetacean graph examples.self_healing_agent:graph \
  --format html --output workflow.html --title "Self-Healing Agent"

# Load a graph from an arbitrary Python file
PYTHONPATH=src autocetacean graph ./my_workflow.py:graph --output workflow.html --format html
```

The Mermaid export marks entry and finish points, shows each node's `LayerKind`, uses dashed labelled arrows for statically recoverable conditional routes, and highlights human `Gate` nodes with a hexagon shape. When `--trace` is supplied, nodes also display execution status badges, retry/rollback counts, and schema violations. The HTML export is one document with inline layout/styles and Mermaid loaded from its public CDN.

### 6. Transactional Workspace Guard (`autocetacean guard`)

Wrap any coding agent, script, or tool command in an atomic snapshot transaction verified by a deterministic gate (e.g. `pytest`):

```bash
autocetacean guard --workspace ./repo \
  --cmd "python agent_edit.py" \
  --gate "pytest -q" \
  --trace-out .autocetacean/traces/run.json --json
```

If the command fails, times out, or fails the gate, AutoCetacean atomically restores every modified, deleted, or newly created file (preserving pre-existing dirty edits) and writes the failure trace.

### 7. MCP Stdio Record & Offline Replay

Record a live stdio MCP server session to JSONL and deterministically replay it offline without spawning the backend server:

```bash
# Record live JSON-RPC 2.0 exchanges
autocetacean mcp-record --trace session.jsonl -- python my_mcp_server.py

# Replay offline in strict mode (returns -32602 / -32601 on drifted tool arguments)
autocetacean mcp-replay --trace session.jsonl --strict
```

See [examples/real_agent_guard_and_mcp_replay.py](examples/real_agent_guard_and_mcp_replay.py) for an end-to-end walkthrough.

## Running the Test Suite

```bash
git clone https://github.com/xunWhale/autocetacean.git && cd autocetacean
pip install -e ".[dev]"
pytest tests/ -v
```

All 92 unit tests execute in <1s with 100% standard library compliance.

## License

MIT License. Designed and engineered by Shen Xun (@xunWhale) · 2026.
