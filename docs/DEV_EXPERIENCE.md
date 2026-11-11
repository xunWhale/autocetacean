# AutoCetacean Developer Experience (DX) & Onboarding Friction Report

## 1. Onboarding Flow Test

Tested against clean virtual environment using wheel distribution (`autocetacean-0.1.0-py3-none-any.whl`):
- **Installation latency**: < 0.8s
- **Zero-dependency audit**: Confirmed 0 transitive packages installed.
- **CLI responsiveness**: `autocetacean --help` and `autocetacean ledger <file> --json` executed cleanly in < 35ms.

## 2. Identified Developer Friction Points (FPs)

### FP-1: Explicit `is_halted` Reset after Node Failure
- **Observation**: When a node fails Layer 3 harness checks, `ctx.is_halted` is set to `True`. If a developer catches the exception and immediately invokes `graph.run(ctx, start_node="recover")`, the engine silently exits because `is_halted` remains truthy.
- **Resolution**: Provide a dedicated `ctx.reset_halt()` helper or automatic recovery resume semantics in `graph.run(..., reset_halt=True)`.

### FP-2: Type Annotations for Dynamic State Variables
- **Observation**: `ctx.state` and `ctx.variables` are typed as `dict[str, Any]`. While flexible, IDE autocompletion is limited during complex multi-node state passing.
- **Resolution**: Support generic state models (e.g. `TypedDict` or `dataclass` state schemas) in future minor releases.

### FP-3: Schema Error Readability
- **Observation**: When `Layer2ContextValidator` encounters a type mismatch, the exception string is clear, but could benefit from pointing out the actual vs expected Python type directly.

## 3. Production Action Items
1. Add `ExecutionContext.resume()` / `reset_halt()` helper methods.
2. Provide typed graph examples in `examples/` directory.
3. Expose pre-configured loop recovery patterns for agent self-healing loops.
