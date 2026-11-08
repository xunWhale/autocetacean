# RFC-001: The Five-Layer Deterministic Runtime for Autonomous Agents

- **Status**: Implemented / Stable
- **Author**: Shen Xun (@xunWhale)
- **Target Version**: AutoCetacean v0.1.0+

## 1. Abstract

Contemporary agent frameworks often treat language model generation as an end-to-end black box. When scaling to long-horizon workflows or autonomous software engineering, stochastic completion leads to three fatal failure modes:
1. **Unbounded Context Drift**: Context windows dilute attention, accumulate conversational noise, and trigger catastrophic forgetting.
2. **Untracked State Side-effects**: Agents issue destructive or malformed tool calls without deterministic pre-execution schema gates.
3. **Non-deterministic Failure Trajectories**: Execution errors trigger erratic recovery attempts without structured checkpoint rollback.

This RFC formalizes a deterministic, five-layer runtime architecture that wraps stochastic LLM completions inside rigid mathematical and engineering constraints.

## 2. The Five Layers

```text
  [ Layer 1: Prompt ]    ──► Stochastic natural language completion (Hypothesis generation)
          │
  [ Layer 2: Context ]   ──► Bounded evidence, schema validation & versioned token budgets
          │
  [ Layer 3: Harness ]   ──► Deterministic test harness, headless verification & CI sandboxes
          │
  [ Layer 4: Loop ]      ──► Audited trajectory, automated rollback & error-directed repair
          │
  [ Layer 5: Graph ]     ──► Resilient state machines, explicit conditional routing & human gates
```

### Layer 1: Prompt (Hypothesis Generation)
The prompt layer generates candidate actions or code modifications. It is treated as strictly untrusted and non-authoritative.

### Layer 2: Context (Bounded Evidence & Schema Gate)
Before any action passes to execution, Layer 2 performs:
- **Token Budget Checks**: Enforces hard upper bounds on context usage.
- **Strict JSON Schema Validation**: Discards malformed tool arguments before subshell or network dispatch.

### Layer 3: Harness (Deterministic Sandbox)
Provides isolated sandboxes for tool execution. Disallows catastrophic system side-effects (e.g. destructive disk operations, unconstrained recursion) and provides deterministic assertions.

### Layer 4: Loop (Audited Trajectory & Repair)
Every state change produces an immutable `StepRecord`. Failures trigger structured retry policies rather than open-ended conversational drift.

### Layer 5: Graph (State Machine Routing)
Directs flow via an explicit `StateGraph`. Routes conditionally based on typed state variables, with support for human approval suspension (`Gate`).

## 3. Persistent Ledger & Rolling Checkpoints

- **Rolling Checkpoints**: State snapshots are serialized at every node boundary. Long tasks can evict raw message history while retaining verified facts in an established background summary.
- **External Structured Ledger**: High-value consensus (user preferences, project constraints, architectural decisions) is committed atomically into versioned slots with rigid byte-size caps.
