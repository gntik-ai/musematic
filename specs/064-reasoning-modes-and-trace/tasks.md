# Tasks: Advanced Reasoning Modes and Trace Export

**Input**: Design documents from `specs/064-reasoning-modes-and-trace/`  
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅ | quickstart.md ✅

**Organization**: Tasks are grouped by user story and preserve current implementation progress. Checked items are already implemented and validated against the corrected design boundary.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared in-progress dependency)
- **[US#]**: Maps to a user story from `spec.md`
- Exact file paths are included in every task

---

## Phase 1: Setup

**Purpose**: Realign design artifacts so runtime contracts match actual service boundaries.

- [X] T001 Audit spec/proto/runtime mismatches and identify the missing contract pieces in `specs/064-reasoning-modes-and-trace/spec.md`, `contracts/proto-changes.md`, and `services/reasoning-engine/proto/reasoning_engine.proto`
- [X] T002 Refresh `plan.md`, `research.md`, `data-model.md`, `contracts/proto-changes.md`, `contracts/rest-api.md`, and `quickstart.md` under `specs/064-reasoning-modes-and-trace/` so DEBATE gets explicit RPCs and budget scope resolution moves to Python
- [X] T003 Update agent context from the refreshed plan via `.specify/scripts/bash/update-agent-context.sh codex`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the shared proto, persistence, and trace-export foundation.

**⚠️ CRITICAL**: User-story implementation depends on this phase.

- [X] T004 Add `SELF_CORRECTION = 7`, `compute_budget`, and `GetReasoningTrace` to `services/reasoning-engine/proto/reasoning_engine.proto`, then regenerate Go stubs in `services/reasoning-engine/proto/api/grpc/v1/` and `services/reasoning-engine/api/grpc/v1/`
- [X] T005 Change `SelectReasoningModeRequest.compute_budget` to `optional double` in `services/reasoning-engine/proto/reasoning_engine.proto`, regenerate all Go bindings, and update presence handling in `services/reasoning-engine/api/grpc/v1/handler.go`
- [X] T006 Add DEBATE session RPCs (`StartDebateSession`, `SubmitDebateTurn`, `FinalizeDebateSession`) and messages to `services/reasoning-engine/proto/reasoning_engine.proto`, then regenerate all Go bindings
- [X] T007 Extend `StartSelfCorrectionRequest` and `CorrectionIterationEvent` with the fields required for trace persistence in `services/reasoning-engine/proto/reasoning_engine.proto`, then regenerate all Go bindings
- [X] T008 [P] Extend `services/reasoning-engine/internal/mode_selector/selector.go`, `internal/mode_selector/heuristic.go`, `internal/events/producer.go`, `pkg/persistence/minio.go`, and `pkg/persistence/postgres.go` for SELF_CORRECTION, reasoning events, and trace metadata helpers
- [X] T009 [P] Create `apps/control-plane/migrations/versions/051_reasoning_trace_export.py` and extend `apps/control-plane/src/platform/execution/models.py`, `schemas.py`, and `exceptions.py` for reasoning trace metadata and API responses
- [X] T010 [P] Implement the Python trace export slice in `apps/control-plane/src/platform/common/clients/reasoning_engine.py`, `src/platform/execution/repository.py`, `service.py`, `router.py`, and the associated tests under `apps/control-plane/tests/unit/execution/` and `tests/integration/execution/`
- [X] T011 [P] Create the new Go debate module in `services/reasoning-engine/internal/debate/` plus its unit tests

**Checkpoint**: The trace-export foundation exists, and the remaining work is concentrated in runtime contract expansion and mode orchestration.

---

## Phase 3: User Story 1 — DEBATE Runtime Sessions (Priority: P1)

**Goal**: The Go reasoning engine exposes explicit DEBATE session RPCs and orchestrates rounds with trace persistence and round-completion events.

**Independent Test**: Start a debate session with 2+ participants, submit turn payloads through the new gRPC contract, finalize it, and verify status, transcript metadata, S3 trace persistence, DB trace metadata, and one `reasoning.debate.round_completed` event per completed round.

- [X] T012 [P] [US1] Implement and validate `DebateSession`, `DebateRound`, consensus detection, and best-effort round event emission in `services/reasoning-engine/internal/debate/`
- [X] T013 [US1] Add DEBATE runtime dependencies to `services/reasoning-engine/api/grpc/v1/handler.go` and `services/reasoning-engine/cmd/reasoning-engine/main.go`
- [X] T014 [US1] Implement `StartDebateSession`, `SubmitDebateTurn`, and `FinalizeDebateSession` in `services/reasoning-engine/api/grpc/v1/handler.go` using `internal/debate.Service`, `pkg/persistence/minio.go`, and `pkg/persistence/postgres.go`
- [X] T015 [P] [US1] Add handler-level DEBATE RPC tests in `services/reasoning-engine/api/grpc/v1/handler_debate_test.go`

**Checkpoint**: DEBATE is no longer only an internal module; it is reachable and auditable through the gRPC surface.

---

## Phase 4: User Story 2 — SELF_CORRECTION Runtime Trace Persistence (Priority: P1)

**Goal**: SELF_CORRECTION captures full iteration payloads and writes consolidated traces that satisfy the export contract.

**Independent Test**: Start a self-correction loop with compute budget and degradation threshold, submit multiple iterations containing prior answer / critique / refined answer payloads, and verify stabilized / degraded / max-iteration traces are persisted and exportable.

- [X] T016 [US2] Extend `services/reasoning-engine/api/grpc/v1/handler.go` to consume the enriched `StartSelfCorrectionRequest` and `CorrectionIterationEvent` payloads, derive runtime config, and persist consolidated SELF_CORRECTION traces
- [X] T017 [P] [US2] Add handler-level SELF_CORRECTION tests in `services/reasoning-engine/api/grpc/v1/handler_self_correction_test.go` covering stabilization, max-iteration termination, degradation detection, and payload-to-trace mapping

**Checkpoint**: SELF_CORRECTION satisfies the spec’s trace requirements rather than only convergence metadata.

---

## Phase 5: User Story 3 — Effective compute_budget Enforcement (Priority: P1)

**Goal**: The control plane resolves the effective budget scope, and Go enforces a single normalized budget with correct omitted-vs-explicit-zero semantics.

**Independent Test**: Configure workflow and step budgets with different values, verify the Python execution layer selects the stricter one, the Go runtime enforces it, and exported traces include `effective_budget_scope` plus correct exhaustion semantics.

- [X] T018 [US3] Resolve workflow-vs-step compute budget precedence in `apps/control-plane/src/platform/execution/` before the reasoning-engine call path, and pass the effective budget downstream
- [X] T019 [US3] Extend `apps/control-plane/src/platform/execution/models.py`, `schemas.py`, `service.py`, and `tests/*execution*` to surface `effective_budget_scope` in stored trace metadata and HTTP responses
- [X] T020 [P] [US3] Add Go and Python tests for omitted budget, explicit zero rejection, out-of-range rejection, and step/workflow precedence in `services/reasoning-engine/api/grpc/v1/handler_budget_test.go` and `apps/control-plane/tests/`

**Checkpoint**: Budget semantics match the spec exactly and are no longer ambiguous at the contract boundary.

---

## Phase 6: User Story 4 — Trace Export Endpoint (Priority: P2)

**Goal**: The execution API returns canonical, paginated reasoning traces for DEBATE, SELF_CORRECTION, and REACT.

**Independent Test**: Export traces for completed and in-progress executions and verify 200/403/404/410 behavior plus technique-specific fields.

- [X] T021 [US4] Implement `GetReasoningTrace` metadata lookup in `services/reasoning-engine/api/grpc/v1/handler.go` and cover it with tests
- [X] T022 [P] [US4] Implement and validate `GET /api/v1/executions/{execution_id}/reasoning-trace` in `apps/control-plane/src/platform/execution/` with unit and integration coverage
- [X] T023 [US4] Extend the trace export contract and Python response models to include `effective_budget_scope` once runtime persistence writes it

**Checkpoint**: Audit/export is live; only the budget-scope addition remains for this story.

---

## Phase 7: User Story 5 — Real-Time Reasoning Events (Priority: P3)

**Goal**: DEBATE round and REACT cycle completion events stream on `runtime.reasoning` without blocking the reasoning pipeline.

**Independent Test**: Run DEBATE and REACT executions with a lagging consumer and verify exact event counts plus unchanged completion latency.

- [X] T024 [US5] Add reasoning event helper methods in `services/reasoning-engine/internal/events/producer.go` and enforce fire-and-forget round emission in `services/reasoning-engine/internal/debate/orchestrator.go`
- [X] T025 [US5] Emit `reasoning.react.cycle_completed` from the REACT execution path in `services/reasoning-engine/api/grpc/v1/handler.go` (or the underlying coordinator path that owns cycle completion)
- [X] T026 [P] [US5] Add tests for REACT cycle event emission and lag-tolerant behavior in `services/reasoning-engine/api/grpc/v1/` or the owning REACT component tests

**Checkpoint**: Both event types are observable in real time with the same non-blocking guarantee.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Validation, regression safety, and final scenario closure.

- [X] T027 [P] Run Go validation on the modified reasoning-engine scope: `go test -race ./...` and golangci-lint on `api/grpc/v1`, `cmd/reasoning-engine`, `internal/debate`, `internal/events`, `internal/mode_selector`, and `pkg/persistence`
- [X] T028 [P] Run Python validation on the trace-export slice: `pytest`, `ruff`, and `mypy --strict` for the modified `apps/control-plane/src/platform/execution/` and client files
- [X] T029 Run the end-to-end quickstart scenarios `S1–S25` once the new DEBATE and SELF_CORRECTION runtime contracts are implemented, and close any remaining regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1**: immediate
- **Phase 2**: blocks all remaining runtime work
- **Phase 3**: depends on updated proto contract from Phase 2
- **Phase 4**: depends on updated self-correction contract from Phase 2
- **Phase 5**: depends on Phase 2 and informs Phase 6 response shape
- **Phase 6**: current base implemented; final budget-scope field depends on Phase 5
- **Phase 7**: DEBATE event base is done; REACT event completion depends on the owning runtime path
- **Phase 8**: after all desired stories are implemented

### Parallel Opportunities

```text
T005 ∥ T006 ∥ T007
T015 ∥ T017 ∥ T020 ∥ T026
```

### Current Suggested MVP for the next implementation pass

1. T005–T007
2. T013–T017
3. T018–T020
4. T023, T025, T026
5. T029
