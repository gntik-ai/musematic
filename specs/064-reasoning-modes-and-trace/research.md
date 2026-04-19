# Research: Advanced Reasoning Modes and Trace Export

**Branch**: `064-reasoning-modes-and-trace` | **Date**: 2026-04-19  
**Feature**: [spec.md](spec.md)

## Decision Log

### D-001: DEBATE enum value already exists in proto

**Decision**: Reuse existing `DEBATE = 6` in `ReasoningMode`; add `SELF_CORRECTION = 7` as the next additive value.

**Rationale**: Preserve proto ordinals and existing consumers.

### D-002: SELF_CORRECTION wraps the existing correction_loop module

**Decision**: Keep convergence and iteration-state logic in `internal/correction_loop/`; extend the external contract only where extra trace payload and policy inputs are missing.

**Rationale**: The loop machinery already exists and should not be duplicated.

### D-003: compute_budget must have presence semantics in proto

**Decision**: Change `SelectReasoningModeRequest.compute_budget` to `optional double compute_budget = 7;`.

**Rationale**: The spec distinguishes “budget omitted” from “budget explicitly set to 0.0”. Plain proto3 `double` cannot express that distinction. `optional` lets the handler reject explicit zero while still treating omission as unconstrained.

**Alternatives considered**: wrapper types. Rejected because `optional double` is simpler and sufficient for presence.

### D-004: Effective budget scope is resolved in Python, not Go

**Decision**: Step-vs-workflow precedence is computed in `apps/control-plane/src/platform/execution/` before the Go call is made. Go receives only the already-effective `compute_budget`.

**Rationale**: Workflow and step configuration live in the control plane, not in the reasoning-engine gRPC contract. This keeps Go focused on enforcement rather than policy resolution.

### D-005: DEBATE needs explicit session RPCs

**Decision**: Add explicit DEBATE RPCs instead of trying to drive debate execution through `SelectReasoningMode`:
- `StartDebateSession`
- `SubmitDebateTurn`
- `FinalizeDebateSession`

**Rationale**: `SelectReasoningMode` is a recommendation RPC. It has no place for participant lists, round limits, or turn payloads. Dedicated session RPCs match the existing `StartSelfCorrectionLoop` / `SubmitCorrectionIteration` pattern.

### D-006: SELF_CORRECTION trace export requires richer iteration payloads

**Decision**: Extend `StartSelfCorrectionRequest` with `step_id`, `optional compute_budget`, and `degradation_threshold`. Extend `CorrectionIterationEvent` with textual iteration payload fields (`prior_answer`, `critique`, `refined_answer`, `iteration_num`).

**Rationale**: The current event only carries quality/cost metadata, which is insufficient to build the trace required by the spec.

### D-007: Trace metadata stays in PostgreSQL; payload stays in object storage

**Decision**: Keep `execution_reasoning_trace_records` as the lookup table and persist consolidated JSON traces in S3-compatible storage.

**Rationale**: Fast metadata lookup plus cheap large-payload storage matches the existing platform pattern.

### D-008: Trace export remains in the execution bounded context

**Decision**: Keep the HTTP endpoint in `apps/control-plane/src/platform/execution/router.py` and read orchestration data via `ExecutionService`.

**Rationale**: Authorization and execution ownership already live there.

### D-009: Real-time events stay on runtime.reasoning

**Decision**: Keep `reasoning.debate.round_completed` and `reasoning.react.cycle_completed` on the existing `runtime.reasoning` topic.

**Rationale**: Additive event types are enough; a new topic adds operational cost without benefit.
