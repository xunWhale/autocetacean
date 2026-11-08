# AutoCetacean

[![CI](https://github.com/xunWhale/autocetacean/actions/workflows/ci.yml/badge.svg)](https://github.com/xunWhale/autocetacean/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Zero-Dependencies](https://img.shields.io/badge/Dependencies-0_Runtime-success.svg)](pyproject.toml)

**The Deterministic Runtime, State-Machine Execution Graph, and Rolling Checkpoint Engine for Autonomous AI Agents.**

> *"Modern agent engineering is not about praying to bigger models — it is about engineering deterministic constraints."*

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

## Running the Test Suite

```bash
git clone https://github.com/xunWhale/autocetacean.git && cd autocetacean
pip install -e ".[dev]"
pytest tests/ -v
```

All 52 unit tests execute in ~0.03s with 100% standard library compliance.

## License

MIT License. Designed and engineered by Shen Xun (@xunWhale) · 2026.
