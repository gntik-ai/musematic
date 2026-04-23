# Implementation Plan: Advanced Reasoning Modes and Trace Export

**Branch**: `064-reasoning-modes-and-trace` | **Date**: 2026-04-19 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/064-reasoning-modes-and-trace/spec.md`

## Summary

Extend the Go reasoning engine with two new runtime capabilities and one audit surface: DEBATE sessions (multi-agent round orchestration) and richer SELF_CORRECTION trace persistence, plus a Python trace export endpoint under `execution/`. The design correction in this pass is to align contracts with the actual runtime boundaries: `compute_budget` must have presence semantics, step-vs-workflow budget resolution belongs in the Python control plane, and DEBATE needs explicit gRPC session RPCs instead of overloading `SelectReasoningMode`.

## Technical Context

**Language/Version**: Go 1.25.x for `services/reasoning-engine`; Python 3.12+ for `apps/control-plane`  
**Primary Dependencies**: gRPC + protobuf, pgx/v5, Redis, Kafka, custom Go persistence helpers, FastAPI, SQLAlchemy 2.x async, Pydantic v2, aioboto3  
**Storage**: PostgreSQL for trace metadata, Redis for hot reasoning state, S3-compatible object storage for consolidated trace artifacts, Kafka for reasoning lifecycle events  
**Testing**: Go `testing` + race detector + golangci-lint; Python `pytest`, `ruff`, `mypy --strict`  
**Target Platform**: Linux containers on Kubernetes; local Docker/testcontainers for integration flows  
**Project Type**: Brownfield modular monolith + Go satellite service  
**Performance Goals**: Trace export p95 under 2 seconds for 200-step traces; reasoning event emission must remain best-effort and non-blocking  
**Constraints**: additive proto evolution only; no rewrites of existing modules; backward-compatible APIs; `compute_budget` omitted means unconstrained while explicit `0` is invalid; workspace/step budget precedence resolved before Go invocation  
**Scale/Scope**: execution-scoped reasoning traces, debate sessions with 2+ participants, self-correction loops with persisted iteration payloads, operator-facing audit export

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Status | Notes |
|------|--------|-------|
| Never rewrite existing code | ✅ PASS | Existing code is extended in place; `internal/debate/` is additive |
| Every schema change uses Alembic | ✅ PASS | Feature continues through migration `051_reasoning_trace_export.py` |
| Preserve existing tests | ✅ PASS | New coverage is additive; current suites stay green |
| Use existing patterns | ✅ PASS | Go keeps existing handler/persistence/event patterns; Python stays inside `execution/` |
| Backward-compatible APIs | ✅ PASS | Proto changes are additive; `compute_budget` gains presence semantics via `optional` |
| Go reasoning engine owns hot-path reasoning | ✅ PASS | Debate orchestration and self-correction loop execution remain in Go |
| Generic S3 storage | ⚠️ NOTE | Python is compliant; Go still extends the pre-existing `pkg/persistence/minio.go` module under brownfield rules |

## Project Structure

### Documentation (this feature)

```text
specs/064-reasoning-modes-and-trace/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── proto-changes.md
│   └── rest-api.md
└── tasks.md
```

### Source Code (repository root)

```text
services/reasoning-engine/
├── proto/reasoning_engine.proto
├── proto/api/grpc/v1/
├── api/grpc/v1/
│   ├── handler.go
│   └── *_test.go
├── cmd/reasoning-engine/main.go
├── internal/
│   ├── debate/
│   ├── events/
│   └── mode_selector/
└── pkg/persistence/

apps/control-plane/
├── migrations/versions/051_reasoning_trace_export.py
├── src/platform/common/clients/reasoning_engine.py
├── src/platform/execution/
│   ├── exceptions.py
│   ├── models.py
│   ├── repository.py
│   ├── router.py
│   ├── schemas.py
│   └── service.py
└── tests/
    ├── unit/execution/
    └── integration/execution/
```

**Structure Decision**: Keep the Go runtime contract and orchestration in `services/reasoning-engine`; keep execution-scoped audit read models and HTTP export in the Python `execution/` bounded context.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Pre-existing Go MinIO client | Existing brownfield storage path | Replacing it in this feature would widen scope beyond reasoning-mode delivery |
