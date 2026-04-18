# Tasks: FQN Namespace System and Agent Identity

**Input**: Design documents from `specs/051-fqn-namespace-agent-identity/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/api-endpoints.md ✅, quickstart.md ✅

**Scope note**: The core FQN system (namespaces, agent FQN field, visibility, discovery endpoints) was shipped in feature 021. US1, US2, and US4 are fully implemented. This update pass addresses **3 genuine gaps** only: event envelope extension, purpose validation tightening, and backfill migration.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Extend the shared event envelope with `agent_fqn`. This is a prerequisite for US1 event wiring.

- [X] T001 Add `agent_fqn: str | None = None` field to `CorrelationContext` Pydantic model in `apps/control-plane/src/platform/common/events/envelope.py`; also update the `make_envelope()` factory function to accept an optional `agent_fqn: str | None = None` keyword argument and pass it through to `CorrelationContext(... agent_fqn=agent_fqn)`

**Checkpoint**: `CorrelationContext` serializes with `agent_fqn` when set, and existing event JSON without `agent_fqn` deserializes without error (Pydantic v2 ignores extra fields by default; default `None` handles missing field).

---

## Phase 2: Foundational — No additional foundational tasks

> US1, US2, and US4 (namespace CRUD, FQN resolution, discovery, visibility) are **already implemented** in `apps/control-plane/src/platform/registry/` from feature 021. No foundational work beyond Phase 1 is required.

---

## Phase 3: US1 — Event Context Wiring (Priority: P1)

**Goal**: Agent lifecycle events produced by the registry service include the agent's FQN in `CorrelationContext`.

**Independent Test**: Publish an agent lifecycle event (`agent.created`). Deserialize the Kafka message envelope. Verify `correlation_context.agent_fqn` equals the agent's FQN string.

- [X] T002 [US1] Update the 4 event publish call sites in `apps/control-plane/src/platform/registry/service.py` to pass `agent_fqn=profile.fqn` to `make_envelope()` (or directly to `CorrelationContext`); locate emit calls for event types `agent.created`, `agent.published`, `agent.deprecated`, and `agent.archived`; pass the `AgentProfile.fqn` value at each site (value is `None` for pre-backfill agents — acceptable, the field is optional)

**Checkpoint**: US1 complete when agent lifecycle events carry `agent_fqn` in the event context.

---

## Phase 4: US3 — Agent Manifest Enrichment: Purpose Validation (Priority: P2)

**Goal**: Enforce 50-character minimum on agent purpose at upload and update time.

**Independent Test**: Attempt to upload an agent manifest with a 49-character purpose — expect HTTP 422 with a validation error message referencing 50 characters. Upload with a 50-character purpose — expect HTTP 201.

- [X] T003 [US3] Update `AgentManifest.purpose` in `apps/control-plane/src/platform/registry/schemas.py` from `Field(min_length=10)` to `Field(min_length=50)`; also check `AgentPatch` schema in the same file — if it has a `purpose` field, update it to `Field(default=None, min_length=50)` for consistency (search for `purpose` in `AgentPatch`)

**Checkpoint**: US3 complete when `AgentManifest` rejects purpose strings shorter than 50 characters.

---

## Phase 5: US5 — Backward-Compatible Agent Migration (Priority: P3)

**Goal**: Create Alembic migration 041 that assigns FQNs to any agents created before the FQN system (namespace_id IS NULL), without downtime, idempotently.

**Independent Test**: Insert a raw `registry_agent_profiles` row with `namespace_id = NULL`, `fqn = NULL`, `display_name = 'old-agent'`. Run `alembic upgrade 041_fqn_backfill`. Verify the agent now has `fqn = 'default:old-agent'`, `namespace_id` set, and `local_name = 'old-agent'`. Run migration again — no error, no duplicate namespace.

- [X] T004 [US5] Create `apps/control-plane/migrations/versions/041_fqn_backfill.py` with `revision = "041_fqn_backfill"` and `down_revision = "040_simulation_digital_twins"`; implement `upgrade()` with three SQL steps: (1) `INSERT INTO registry_namespaces (id, workspace_id, name, created_by, created_at, updated_at) SELECT gen_random_uuid(), a.workspace_id, 'default', a.created_by, now(), now() FROM registry_agent_profiles a WHERE a.namespace_id IS NULL AND a.deleted_at IS NULL GROUP BY a.workspace_id, a.created_by ON CONFLICT DO NOTHING`; (2) UPDATE registry_agent_profiles setting `namespace_id`, `local_name` (slugified display_name: lowercase, spaces/special chars → hyphens, strip leading/trailing hyphens), and `fqn = 'default:' || local_name` for all rows WHERE `namespace_id IS NULL AND deleted_at IS NULL`; handle slug collisions by appending `-2`, `-3`, etc. using a window function `ROW_NUMBER() OVER (PARTITION BY workspace_id, derived_slug)`; (3) `UPDATE registry_agent_profiles SET needs_reindex = true WHERE length(purpose) < 50 AND deleted_at IS NULL AND needs_reindex = false`; implement `downgrade()` as no-op (`pass`)

**Checkpoint**: US5 complete when migration runs cleanly on a database with pre-FQN agents and assigns valid, unique FQNs to all of them.

---

## Phase 6: Polish and Tests

**Purpose**: Unit and integration tests for the 3 changed/new artefacts. Existing tests for US1/US2/US4 endpoints pass unchanged — no regressions.

- [X] T005 [P] Write unit tests in `apps/control-plane/tests/unit/common/test_envelope.py`: (1) `test_correlation_context_with_agent_fqn` — instantiate with `agent_fqn="finance-ops:kyc-verifier"`, serialize to JSON, verify field present; (2) `test_correlation_context_without_agent_fqn` — instantiate without `agent_fqn`, verify `agent_fqn` is `None`; (3) `test_correlation_context_backwards_compatible` — deserialize existing JSON without `agent_fqn` key, verify no `ValidationError` and `agent_fqn` is `None`
- [X] T006 [P] Write unit tests in `apps/control-plane/tests/unit/registry/test_purpose_validation.py`: (1) `test_manifest_purpose_too_short` — `AgentManifest(purpose="A"*49, ...)` raises `ValidationError`; (2) `test_manifest_purpose_exactly_50` — `AgentManifest(purpose="A"*50, ...)` succeeds; (3) `test_manifest_purpose_above_50` — `AgentManifest(purpose="A"*100, ...)` succeeds; (4) `test_manifest_purpose_old_min_rejected` — `AgentManifest(purpose="A"*10, ...)` raises `ValidationError` (confirms old min no longer accepted)
- [X] T007 [US5] Write integration tests in `apps/control-plane/tests/integration/registry/test_fqn_backfill.py`: set up a test PostgreSQL database, insert 3 agent rows with `namespace_id=NULL` (one with `display_name='old agent'` with spaces, one with purpose <50 chars, one already has FQN), run migration via `alembic upgrade 041_fqn_backfill`, assert: all null-namespace agents have FQN set; display_name with spaces produces slugified local_name; already-FQN'd agent is untouched; agent with short purpose has `needs_reindex=true`; running migration twice produces no error and no duplicate namespaces

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 3 (US1)**: Depends on Phase 1 (T001 must exist before T002 passes `agent_fqn` to `make_envelope()`)
- **Phase 4 (US3)**: Independent of Phase 1 — can start in parallel with Phase 3
- **Phase 5 (US5)**: Independent — no dependencies on T001–T003
- **Phase 6 (Tests)**: T005 depends on T001; T006 depends on T003; T007 depends on T004

### User Story Dependencies

- **US1**: Depends on Phase 1 (envelope change)
- **US2**: Already implemented — no tasks
- **US3**: Independent of all other tasks
- **US4**: Already implemented — no tasks
- **US5**: Independent of all other tasks

### Parallel Opportunities

```bash
# T003 and T004 can run in parallel (different files, no inter-dependency)
T003 schemas.py purpose validation  |  T004 migration 041

# T005 and T006 can run in parallel (different test files)
T005 test_envelope.py  |  T006 test_purpose_validation.py

# T007 depends on T004 (migration must exist before integration test)
# Run after T004 completes
```

---

## Implementation Strategy

### MVP (US1 + US3 — Phases 1, 3, 4)

1. T001: Add `agent_fqn` to envelope
2. T002: Wire `agent_fqn` into registry service events
3. T003: Tighten purpose validation
4. **VALIDATE**: Run existing test suite — all existing tests pass, new validation rejects short purposes

### Full Feature (All Phases)

1. MVP (T001–T003) → validate
2. T004: Migration 041 — run against staging database
3. T005–T007: Tests
4. Deploy: `alembic upgrade head` as part of release

### Parallel Team Strategy

- Developer A: T001 → T002 (envelope + service wiring)
- Developer B: T003 + T006 (schema validation + its unit test)
- Developer C: T004 + T007 (migration + its integration test)
- T005 can be done by any developer after T001 is merged

---

## Notes

- [P] tasks = different files, no inter-task dependencies — safe to parallelize
- Only T002 has a strict sequencing dependency (needs T001 merged first)
- US1, US2, US4 are **already implemented** — no tasks generated for them to avoid duplicate work
- The total implementation surface is intentionally small: 2 file modifications + 1 new file + 3 test files
- Run `alembic upgrade head` in the migration test environment before deploying to production
