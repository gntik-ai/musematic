# Implementation Plan: FQN Namespace System and Agent Identity

**Branch**: `051-fqn-namespace-agent-identity` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/051-fqn-namespace-agent-identity/spec.md`

## Summary

The FQN namespace system, agent visibility configuration, and FQN-based discovery are already shipped in the existing codebase (feature 021 — Agent Registry & Ingest). This update pass adds the three genuine gaps: (1) `agent_fqn` field in `CorrelationContext` event envelope, (2) purpose minimum length update from 10 to 50 characters, and (3) a backfill migration assigning FQNs to any pre-existing agents without namespace assignment. Total scope: 2 file modifications + 1 new migration file + tests.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+
**Storage**: PostgreSQL 16 (schema changes via Alembic migration 041)
**Testing**: pytest + pytest-asyncio 8.x, min 95% coverage on modified files
**Target Platform**: Linux / Kubernetes (same as control plane)
**Project Type**: Brownfield modification to existing Python web service
**Performance Goals**: No new hot paths introduced; migration 041 runs offline with zero downtime
**Constraints**: Brownfield Rules 1–8; no file rewrites; backward-compatible API changes only; all changes via Alembic
**Scale/Scope**: 2 modified files, 1 new migration, 1 new test module

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Modular monolith (Principle I) | ✅ PASS | All changes within `registry/` bounded context and `common/events/`; no new services |
| No cross-boundary DB access (Principle IV) | ✅ PASS | Only modifying `registry/` context tables + event envelope (common shared model) |
| Policy is machine-enforced (Principle VI) | ✅ PASS | Visibility configuration is stored; enforcement remains in existing policy engine |
| Agent identity uses FQN as primary (Principle VIII) | ✅ PASS | This feature reinforces it |
| Zero-trust default visibility (Principle IX) | ✅ PASS | Default `visibility_agents: []` preserved |
| Secrets not in LLM context (Principle XI) | ✅ PASS | N/A for this feature |
| Generic S3 storage (Principle XVI) | ✅ PASS | No S3 interaction in this feature |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | Only additive changes to 2 files + 1 new migration |
| Brownfield Rule 2 (Alembic only) | ✅ PASS | Migration 041 handles all data changes |
| Brownfield Rule 7 (backward-compatible) | ✅ PASS | `agent_fqn` is optional with default None; purpose validation only affects new uploads |

**Post-design re-check**: No violations. Migration 041 is non-destructive and idempotent.

## Project Structure

### Documentation (this feature)

```text
specs/051-fqn-namespace-agent-identity/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api-endpoints.md # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code — What Changes

```text
apps/control-plane/
├── src/platform/
│   ├── common/events/
│   │   └── envelope.py                   MODIFIED — add agent_fqn: str | None = None
│   └── registry/
│       └── schemas.py                    MODIFIED — purpose min_length 10 → 50
│
├── migrations/versions/
│   └── 041_fqn_backfill.py               NEW — backfill default namespace + FQNs
│
└── tests/
    └── integration/registry/
        └── test_fqn_backfill.py          NEW — integration tests for migration + validation

# Everything else is UNCHANGED (already shipped in feature 021):
# apps/control-plane/src/platform/registry/models.py      (AgentNamespace, AgentProfile)
# apps/control-plane/src/platform/registry/service.py     (RegistryService)
# apps/control-plane/src/platform/registry/router.py      (all endpoints)
# apps/control-plane/src/platform/registry/repository.py  (queries + FQN pattern matching)
```

**Structure Decision**: Strict additive changes only. The existing `registry/` bounded context already has the full FQN implementation. The only modifications are to `envelope.py` (shared infrastructure) and `schemas.py` (validation tightening).

## Implementation Phases

### Phase 1: Event Envelope Extension

**Goal**: Add `agent_fqn` to `CorrelationContext`.

**Files**:
- `apps/control-plane/src/platform/common/events/envelope.py` — add `agent_fqn: str | None = None` field to `CorrelationContext` Pydantic model; add field to `make_envelope()` factory signature as optional kwarg

**Independent test**: Unit test — serialize/deserialize `CorrelationContext` with and without `agent_fqn`; verify existing event JSON without `agent_fqn` deserializes without error.

---

### Phase 2: Purpose Validation Tightening

**Goal**: Enforce 50-character minimum on agent purpose.

**Files**:
- `apps/control-plane/src/platform/registry/schemas.py`:
  - `AgentManifest.purpose`: change `Field(min_length=10)` → `Field(min_length=50)`
  - `AgentPatch`: if `purpose` is a patchable field, add `Field(default=None, min_length=50)` for consistency

**Independent test**: Unit test — validate `AgentManifest` with purpose lengths 49, 50, 51 chars; verify 49 raises `ValidationError`, 50 and 51 pass.

---

### Phase 3: Backfill Migration

**Goal**: Assign FQNs to any agents without `namespace_id` (pre-FQN-system agents).

**Files**:
- `apps/control-plane/migrations/versions/041_fqn_backfill.py`:
  - `revision = "041_fqn_backfill"`, `down_revision = "040_simulation_digital_twins"`
  - `upgrade()`: Create "default" namespace per workspace for namespace-less agents (ON CONFLICT DO NOTHING); assign `namespace_id`, `local_name`, `fqn`; handle slug collision within namespace by appending `-N` suffix; flag agents with `len(purpose) < 50` as `needs_reindex = true`
  - `downgrade()`: no-op (data migration is one-way)

**Independent test**: Integration test — insert raw agent row with `namespace_id = NULL`; run migration; verify FQN assigned; re-run migration (idempotency); verify no error and no duplicate namespace.

---

### Phase 4: Test Coverage and Agent Event Integration

**Goal**: Confirm existing endpoints still pass all tests; confirm `agent_fqn` is set correctly by registry event publishers.

**Files**:
- `apps/control-plane/tests/integration/registry/test_fqn_backfill.py` — per quickstart.md test cases for US1–US5
- `apps/control-plane/tests/unit/test_envelope.py` — `CorrelationContext` serialization tests
- Update `apps/control-plane/src/platform/registry/service.py` event publish calls to pass `agent_fqn=agent.fqn` in the `correlation_context` kwarg when publishing agent lifecycle events (e.g., `agent.created`, `agent.published`)

**Note on service.py update**: This is a single-line change per event emit call in `RegistryService`. The brownfield rule allows targeted line-level modifications within an existing file.

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|----------|--------|--------|
| `POST /api/v1/namespaces` | Existing | No change |
| `GET /api/v1/namespaces` | Existing | No change |
| `DELETE /api/v1/namespaces/{id}` | Existing | No change |
| `POST /api/v1/agents/upload` | Existing | Validation tightened (purpose 50+) |
| `GET /api/v1/agents/resolve/{fqn}` | Existing | No change |
| `GET /api/v1/agents?fqn_pattern=...` | Existing | No change |
| `PATCH /api/v1/agents/{id}` | Existing | No change |
| Kafka events (all topics) | Existing | `CorrelationContext` gains `agent_fqn` field |

## Dependencies

- **Feature 021** (Agent Registry & Ingest): Provides the base implementation. Already deployed.
- **No dependencies on other update-pass features**: This feature is self-contained.

## Complexity Tracking

No constitution violations. No complexity justification table needed.

The implementation is intentionally minimal: 2 file modifications + 1 migration. The user-provided plan described 13 steps because it assumed a greenfield implementation; research revealed features 1–12 are already shipped.
