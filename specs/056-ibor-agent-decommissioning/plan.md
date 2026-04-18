# Implementation Plan: IBOR Integration and Agent Decommissioning

**Branch**: `056-ibor-integration-and` | **Date**: 2026-04-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/056-ibor-agent-decommissioning/spec.md`

## Summary

The platform has an RBAC engine (`RBACEngine` in `auth/rbac.py` using `UserRole`/`RolePermission` tables) but no mechanism to import identity from enterprise systems, and an agent registry (`AgentProfile` with `LifecycleStatus` enum covering 6 values through `archived`) but no terminal state with operational shutdown semantics. This feature delivers two additive capabilities: (1) a configurable **IBOR connector** supporting LDAP, OIDC, and SCIM with pull and push sync modes, per-user reconciliation, partial-success handling, and audit records; (2) a formal **`decommissioned` lifecycle state** with mandatory reason, instance shutdown delegation to Runtime Controller, cross-surface invisibility, history preservation, and irreversible-by-design semantics. Total scope: 1 Alembic migration (044) adding 1 enum value + 4 columns + 2 new tables; 13 modified Python files; 2 new Python service modules (`auth/ibor_sync.py`, `auth/ibor_service.py`); 8 new Python test modules. No new Kafka topics (reuses `registry.events` and `auth.events`). No new bounded contexts. Feature-flag-like safety built in via FR-019/FR-020 + SC-008.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic, aiokafka 0.11+ (events), redis-py 5.x async (sync-lock), APScheduler 3.x (periodic sync), `ldap3` 2.9+ (LDAP adapter — NEW dependency), httpx 0.27+ (OIDC/SCIM adapters), pytest + pytest-asyncio 8.x
**Storage**: PostgreSQL — 2 new tables (`ibor_connectors`, `ibor_sync_runs`), 4 new columns across existing tables, 1 new enum value on `registry_lifecycle_status`; no new data stores
**Testing**: pytest + pytest-asyncio 8.x; min 95% coverage on modified files; migration roundtrip test (up + down)
**Target Platform**: Linux / Kubernetes (same as control plane)
**Project Type**: Brownfield modification to existing Python web service
**Performance Goals**: Initial pull sync of 500-user population < 5 min (SC-001); incremental sync < 60 s (SC-002); decommission action < 60 s p95 for up to 5 running instances (SC-004); cross-surface invisibility propagation < 60 s (SC-005)
**Constraints**: Brownfield Rules 1–8; no file rewrites; additive + backward-compatible only; credentials via reference only (FR-016); decommissioned is irreversible by policy (FR-013)
**Scale/Scope**: 13 modified Python source files, 2 new service modules, 1 Alembic migration, 8 new test modules, 1 new library dependency (ldap3)

## Constitution Check

**GATE: Must pass before implementation**

| Principle | Status | Notes |
|-----------|--------|-------|
| Modular monolith (Principle I) | ✅ PASS | Changes confined to `auth/` and `registry/` bounded contexts; no cross-boundary coupling beyond existing `registry → runtime_controller` gRPC call pattern |
| No cross-boundary DB access (Principle IV) | ✅ PASS | `auth/` owns `ibor_connectors`, `ibor_sync_runs`, and the new `user_roles.source_connector_id` column; `registry/` owns the 3 new agent profile columns; no cross-context queries |
| Policy is machine-enforced (Principle VI) | ✅ PASS | Decommission authorization enforced via `RBACEngine.check_permission()`; state transition enforced via existing `is_valid_transition()` |
| Zero-trust (Principle IX) | ✅ PASS | All admin endpoints require `platform_admin`; workspace-scoped endpoints require `workspace_owner` or `platform_admin` |
| Secrets not in LLM context (Principle XI) | ✅ PASS | N/A to this feature; credentials resolved only at sync-time via K8s Secret reference, never exposed in REST responses (FR-016) |
| Generic S3 storage (Principle XVI) | ✅ PASS | N/A to this feature |
| Brownfield Rule 1 (no rewrites) | ✅ PASS | All existing files are line-level modifications; 2 new files are new additive services |
| Brownfield Rule 2 (Alembic only) | ✅ PASS | Single migration 044 covers enum value addition, new columns, new tables |
| Brownfield Rule 3 (preserve tests) | ✅ PASS | 8 new test modules; no existing tests modified |
| Brownfield Rule 4 (use existing patterns) | ✅ PASS | APScheduler pattern from 022/025/034; Redis lock pattern from 028; event producer pattern from existing `registry/events.py` and `auth/events.py`; flat-file auth modules preserved |
| Brownfield Rule 5 (reference existing files) | ✅ PASS | All modified files cited with exact function names in data-model.md |
| Brownfield Rule 6 (additive enum values) | ✅ PASS | `decommissioned` added to existing `LifecycleStatus` via `ADD VALUE IF NOT EXISTS`; never recreated |
| Brownfield Rule 7 (backward-compatible APIs) | ✅ PASS | New columns nullable/defaulted; new endpoints opt-in; existing endpoints retain behavior when no connectors/decommissions exist (FR-019, FR-020) |
| Brownfield Rule 8 (feature flags) | ✅ PASS | Effective feature flag via FR-019/FR-020: system behaves as pre-feature when `ibor_connectors` is empty AND no agents are in `decommissioned` status; gradual rollout inherent |

**Post-design re-check**: No violations.

## Project Structure

### Documentation (this feature)

```text
specs/056-ibor-agent-decommissioning/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── contracts.md     # Phase 1 output
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code — What Changes

```text
apps/control-plane/
├── src/platform/
│   ├── auth/
│   │   ├── models.py                 MODIFIED — add source_connector_id to UserRole;
│   │   │                                         add IBORConnector, IBORSyncRun, 3 enums
│   │   ├── schemas.py                MODIFIED — add IBORConnectorCreate/Response,
│   │   │                                         IBORRoleMappingRule, IBORSyncRunResponse
│   │   ├── rbac.py                   MODIFIED — add revoke_connector_sourced_roles() helper
│   │   ├── repository.py             MODIFIED — add connector/sync-run CRUD;
│   │   │                                         add list_user_roles_by_connector()
│   │   ├── events.py                 MODIFIED — add publish_ibor_sync_completed()
│   │   ├── router.py                 MODIFIED — add 7 IBOR endpoints (CRUD + sync + runs)
│   │   ├── dependencies.py           MODIFIED — add get_ibor_service, get_ibor_sync_service
│   │   ├── ibor_service.py           NEW — IBORConnectorService (CRUD)
│   │   └── ibor_sync.py              NEW — IBORSyncService (LDAP/OIDC/SCIM sync engine)
│   │
│   └── registry/
│       ├── models.py                 MODIFIED — add decommissioned to LifecycleStatus enum;
│       │                                         add 3 columns to AgentProfile
│       ├── schemas.py                MODIFIED — add AgentDecommissionRequest/Response
│       ├── state_machine.py          MODIFIED — add decommissioned transitions (additive)
│       ├── service.py                MODIFIED — add decommission_agent(); extend list filters
│       ├── repository.py             MODIFIED — extend list predicates to exclude decommissioned;
│       │                                         persist decommission fields
│       ├── events.py                 MODIFIED — add publish_agent_decommissioned()
│       └── router.py                 MODIFIED — add POST /.../decommission endpoint
│
├── migrations/versions/
│   └── 044_ibor_and_decommission.py  NEW — 1 enum value + 4 columns + 2 tables
│
└── tests/
    └── unit/
        ├── auth/
        │   ├── test_ibor_connector_crud.py       NEW — connector CRUD endpoints
        │   ├── test_ibor_sync_pull.py            NEW — pull sync scenarios (6)
        │   ├── test_ibor_sync_push.py            NEW — push sync scenarios (2)
        │   └── test_rbac_source_connector.py     NEW — manual vs IBOR-sourced preservation
        └── registry/
            ├── test_decommission_service.py      NEW — decommission action scenarios (6)
            ├── test_decommission_state_machine.py NEW — transition rules
            ├── test_decommission_visibility.py   NEW — list/search exclusion
            └── test_decommission_router.py       NEW — REST contract
```

**Structure Decision**: Additive changes to 2 bounded contexts (`auth/`, `registry/`) + 1 Alembic migration + 2 new Python service modules (flat files in `auth/`, matching the established pattern) + 8 new Python test modules. No new bounded contexts, no new data stores, no new Kafka topics.

## Implementation Phases

### Phase 1: Migration 044 (blocks all implementation phases)

**Goal**: Add `decommissioned` enum value + 3 agent profile columns + 1 user_roles column + 2 new IBOR tables.

**Files**:
- `apps/control-plane/migrations/versions/044_ibor_and_decommission.py` — `revision = "044_ibor_and_decommission"`, `down_revision = "043_runtime_warm_pool_targets"`; upgrade adds enum value, columns, tables; downgrade drops tables and columns (enum value is left in place per PostgreSQL limitation, documented in migration comment).

**Independent test**: `alembic upgrade 044_ibor_and_decommission` applies cleanly; assert table + column existence; downgrade; assert tables and columns removed.

---

### Phase 2: Registry decommissioning — model, state machine, service, endpoint (US3 + US4 + US5 — P1/P1/P2)

**Goal**: Agents can be decommissioned with a reason; the terminal state enforces shutdown, invisibility, and irreversibility.

**Prerequisites**: Phase 1 (migration)

**Files**:
- `registry/models.py` — append `decommissioned` to `LifecycleStatus`; add 3 columns to `AgentProfile`
- `registry/schemas.py` — add `AgentDecommissionRequest`, `AgentDecommissionResponse`
- `registry/state_machine.py` — add transitions (every non-terminal → `decommissioned`; `decommissioned → {}`)
- `registry/service.py` — add `decommission_agent()` method; extend list/search methods to exclude `decommissioned` where `archived` is excluded
- `registry/repository.py` — extend list predicates; add decommission persistence (uses existing commit pattern)
- `registry/events.py` — add `publish_agent_decommissioned()` helper
- `registry/router.py` — add `POST /{workspace_id}/agents/{agent_id}/decommission`

**Independent test**:
- Decommission agent with 2 active instances → instances stopped via mock RuntimeController, status terminal, reason persisted, event published
- Invalid state transition (decommissioned → published) rejected by state machine
- List/search APIs exclude decommissioned agents
- Audit queries return decommissioned agents

---

### Phase 3: IBOR connector models + CRUD (US1/US2 foundation — P1/P2)

**Goal**: Admins can create, list, update, and delete IBOR connectors via REST. Configuration persists and credential values are never exposed.

**Prerequisites**: Phase 1 (migration — IBOR tables)

**Files**:
- `auth/models.py` — add `IBORConnector`, `IBORSyncRun`, 3 new enums (`IBORSourceType`, `IBORSyncMode`, `IBORSyncRunStatus`); add `source_connector_id` to `UserRole`
- `auth/schemas.py` — add 4 schemas (Create, Response, RoleMappingRule, SyncRunResponse)
- `auth/repository.py` — add CRUD queries for connectors and sync runs
- `auth/ibor_service.py` (NEW) — `IBORConnectorService` with 6 methods (create/list/get/update/delete/list_sync_runs)
- `auth/router.py` — add 6 endpoints (CRUD + list_runs)
- `auth/dependencies.py` — add `get_ibor_service`

**Independent test**: Create connector → 201 + redacted credential_ref; list → 200 with items; update → 200; delete → 204 (sets `enabled=false`; history preserved); list runs → 200 + 90-most-recent paginated.

---

### Phase 4: IBOR sync engine — LDAP/OIDC/SCIM pull (US1 — P1)

**Goal**: Scheduled and on-demand pull sync runs against configured connectors; per-user reconciliation with partial-success tolerance.

**Prerequisites**: Phase 3 (connector CRUD must exist)

**Files**:
- `auth/ibor_sync.py` (NEW) — `IBORSyncService` with:
  - `run_sync()` — main entry point; Redis lock `ibor:sync:{connector_id}` (conflict → 409)
  - `_pull_ldap()` via `ldap3` library
  - `_pull_oidc()` via httpx (admin/userinfo + groups API)
  - `_pull_scim()` via httpx (`/Users`, `/Groups`)
  - `_reconcile_user_roles()` — per-user role reconciliation honoring `source_connector_id`
  - `_resolve_credential()` — reads K8s Secret via existing pattern
- `auth/rbac.py` — add `revoke_connector_sourced_roles()` helper
- `auth/router.py` — add `POST /.../connectors/{id}/sync` (on-demand trigger)
- `auth/events.py` — add `publish_ibor_sync_completed()`
- `auth/dependencies.py` — add `get_ibor_sync_service`
- APScheduler registration in the main FastAPI app factory (existing pattern; loads connectors at startup and schedules per `cadence_seconds`)

**Independent test**: Pull sync imports role mapping; role revoked when user removed from group; manual assignment preserved; partial-success reported on mixed results; concurrent trigger rejected.

---

### Phase 5: IBOR push sync (US2 — P2)

**Goal**: Push-mode SCIM sync exports active and decommissioned agents to the configured IBOR endpoint for compliance reporting.

**Prerequisites**: Phase 4 (sync engine foundation)

**Files**:
- `auth/ibor_sync.py` — add `_push_scim()` method; `run_sync()` dispatches to push adapter when `mode=push`
- Existing connector schema already supports `sync_mode=push`; no additional schema changes

**Independent test**: Push sync creates SCIM records for all 3 active agents; decommissioning an agent then running push marks it inactive in SCIM.

---

### Phase 6: Tests — comprehensive coverage

**Goal**: All new code paths covered by unit tests.

**Files**: 8 test modules listed in the structure section, covering the 21 scenarios in `quickstart.md`.

---

## API Endpoints Used / Modified

| Endpoint | Status | Change |
|---|---|---|
| `POST /api/v1/registry/{workspace_id}/agents/{agent_id}/decommission` | **NEW** | Decommission action |
| `POST /api/v1/registry/{workspace_id}/agents/{agent_id}/transition` | Existing | Now rejects `decommissioned` → any |
| `GET /api/v1/registry/{workspace_id}/agents` | Existing | Excludes `decommissioned` by default |
| `GET /api/v1/marketplace/search` | Existing | Excludes `decommissioned` |
| `POST /api/v1/auth/ibor/connectors` | **NEW** | Connector create |
| `GET /api/v1/auth/ibor/connectors` | **NEW** | List connectors |
| `GET/PUT/DELETE /api/v1/auth/ibor/connectors/{id}` | **NEW** | CRUD |
| `POST /api/v1/auth/ibor/connectors/{id}/sync` | **NEW** | On-demand sync trigger |
| `GET /api/v1/auth/ibor/connectors/{id}/runs` | **NEW** | Sync run history |
| `registry.events` Kafka topic | Existing | Now also carries `agent_decommissioned` |
| `auth.events` Kafka topic | Existing | Now also carries `ibor_sync_completed` |

## Dependencies

- **Feature 014 (Auth bounded context)**: Provides `UserRole`, `RolePermission`, `RBACEngine`. Extended by Phase 3/4.
- **Feature 021 (Agent Registry)**: Provides `AgentProfile`, `LifecycleStatus`, state machine. Extended by Phase 2.
- **Feature 009 (Runtime Controller)**: Provides `StopRuntime` gRPC RPC for instance shutdown. Used by Phase 2.
- **Feature 055 (Runtime Warm Pool)**: Migration 043 is `down_revision` for 044. K8s-Secret resolution pattern reused for `credential_ref`.
- **APScheduler**: Already a project dependency (022/025/034). Used for periodic sync.
- **NEW**: `ldap3` Python library (≥ 2.9) for LDAP adapter. Additive dependency.

## Complexity Tracking

No constitution violations. No complexity justification required.

| Category | Count |
|---|---|
| Modified Python source files | 13 (7 in `auth/`, 6 in `registry/`) |
| New Python service modules | 2 (`auth/ibor_sync.py`, `auth/ibor_service.py`) |
| New Alembic migrations | 1 (044 — enum + columns + 2 tables) |
| New Python test modules | 8 |
| New bounded contexts | 0 |
| New database tables | 2 (`ibor_connectors`, `ibor_sync_runs`) |
| New Kafka topics | 0 |
| New REST API endpoints | 8 (1 registry + 7 auth) |
| New library dependencies | 1 (`ldap3`) |

User input refinements discovered during research:

1. User step 2 path `auth/services/ibor_sync.py` is incorrect — `auth/` uses flat files (`auth/ibor_sync.py`). Corrected in data-model.md.
2. User step 5 path `auth/services/rbac_service.py` is incorrect — existing module is `auth/rbac.py` (class `RBACEngine`). Corrected.
3. User plan omits the `source_connector_id` column on `user_roles`, which is required for FR-003 (manual assignment preservation). Added to migration 044.
4. User plan omits the `ibor_connectors` and `ibor_sync_runs` tables, both required for connector lifecycle and audit (FR-001, FR-006, FR-018). Added to migration 044.
5. User plan omits the state machine update; decommissioning needs transitions defined in `state_machine.py` or will be rejected by `is_valid_transition()`. Added in Phase 2.
6. User plan omits OpenSearch filter updates for marketplace invisibility (FR-011, US5); extended list predicates cover this in Phase 2 without new indexes.
7. User plan's "Estimated Effort: 2 story points (~1 day)" appears optimistic given the actual scope (13 modified files, 2 new services, 2 new tables, LDAP/OIDC/SCIM adapters, 8 test modules); the plan does not re-estimate effort but flags the expanded scope.
