# Research: IBOR Integration and Agent Decommissioning

**Feature**: `specs/056-ibor-agent-decommissioning/spec.md`
**Date**: 2026-04-18
**Phase**: 0 — Unknowns resolved, no NEEDS CLARIFICATION markers remain

---

## Decision 1: User-plan file paths are incorrect — auth/ is flat, not packaged

**Decision**: Place new IBOR code as flat files under `apps/control-plane/src/platform/auth/` (e.g., `auth/ibor_sync.py`, `auth/ibor_service.py`), not `auth/services/ibor_sync.py`.

**Rationale**: The `auth/` bounded context uses flat files: `models.py`, `service.py`, `rbac.py`, `repository.py`, `router.py`, `schemas.py`, `session.py`, `mfa.py`, `password.py`, `tokens.py`, `lockout.py`, `purpose.py`, `events.py`, `exceptions.py`, `dependencies.py`. There is no `auth/services/` subdirectory. Creating one would diverge from the established pattern (Brownfield Rule 4). Similarly the user's reference to `rbac_service.py` refers to the existing `rbac.py` (`RBACEngine` class).

**Alternatives considered**: Introducing an `auth/services/` subpackage — rejected; 13 flat-file modules already define the pattern; adding a new layer would violate Brownfield Rule 1 by restructuring existing code.

---

## Decision 2: Existing state machine requires two targeted additions — `decommissioned` transitions

**Decision**: Extend `VALID_REGISTRY_TRANSITIONS` in `registry/state_machine.py` to allow `published → decommissioned`, `disabled → decommissioned`, `deprecated → decommissioned`, `archived → decommissioned`, and `draft → decommissioned` (edge case: decommission before publish). Set `decommissioned → set()` (terminal, FR-013).

**Rationale**: The existing state machine (`draft → validated → published → {disabled, deprecated}`, `disabled → published`, `deprecated → archived`, `archived → {}`) defines all legal transitions. Adding a terminal `decommissioned` state requires entries for every non-terminal status (decommission is always legal) and `decommissioned → {}` is terminal. `validated` is an intermediate state where decommissioning is meaningless (agent not yet in use); we include `validated → decommissioned` for operator escape-hatch completeness but expect it rare.

Re-activation (FR-013 + FR-014) works by NOT adding any `decommissioned → X` transitions — the state machine enforces immutability.

**Alternatives considered**: Bypassing the state machine for decommissioning — rejected; every lifecycle change must go through `is_valid_transition()` for audit coherence. A separate `decommissions` audit table — rejected; the existing `registry_lifecycle_audit` table already records all state changes with `previous_status`, `new_status`, `actor_id`, `reason`; the decommission `reason` field stores the `decommission_reason`.

---

## Decision 3: New columns on existing tables, no replacement

**Decision**: Add 3 columns to `registry_agent_profiles` and 1 column to `user_roles` via Alembic migration 044.

**Rationale**: Brownfield Rule 7 requires backward-compatible, nullable new fields. Adding `decommissioned_at TIMESTAMPTZ NULL`, `decommission_reason TEXT NULL`, `decommissioned_by UUID NULL` preserves every existing row. For `user_roles`, adding `source_connector_id UUID NULL` distinguishes IBOR-sourced assignments from manual admin assignments — the NULL default means every existing row is classified as "manual" without any data migration.

**Alternatives considered**: A separate `agent_decommissions` table — rejected; Brownfield Rule 1 (never rewrite); the fields logically belong to `AgentProfile` and are queried together. A separate `user_role_sources` table — rejected; introduces an unnecessary join in the hot-path RBAC check.

---

## Decision 4: Two new tables for IBOR connector lifecycle and audit

**Decision**: Create two tables via migration 044: `ibor_connectors` (configuration) and `ibor_sync_runs` (per-run audit).

**Rationale**: Connector configuration is shared across sync runs and needs to be queryable/editable independently of any run. Sync run audit is append-only, has its own retention concerns, and is queried by `connector_id` + `started_at` range. Putting run data into a JSONB field on the connector would violate the 90-most-recent pagination requirement (FR-018) and make audit queries expensive.

**Schema**:
```
ibor_connectors (id, name, source_type, sync_mode, cadence, credential_ref,
                 role_mapping_policy JSONB, enabled, created_by, created_at,
                 last_run_at, last_run_status)
ibor_sync_runs  (id, connector_id FK, mode, started_at, finished_at, status,
                 counts JSONB, error_details JSONB, triggered_by)
```

**Alternatives considered**: Single table with JSON arrays — rejected (retention, queryability). Using the generic `audit_events` table — rejected; sync-run records need structured fields (`counts`, `error_details`) that benefit from JSONB columns with known keys, not free-form audit envelopes.

---

## Decision 5: `LifecycleStatus` enum additive via Alembic (Brownfield Rule 6)

**Decision**: Migration 044 issues `ALTER TYPE registry_lifecycle_status ADD VALUE IF NOT EXISTS 'decommissioned'`; Python enum gets `decommissioned = "decommissioned"` appended.

**Rationale**: Existing enum values (`draft | validated | published | disabled | deprecated | archived`) are stable — Brownfield Rule 6 forbids recreating the enum. `ADD VALUE IF NOT EXISTS` is the canonical PostgreSQL pattern for additive enum extension.

**Alternatives considered**: Using a string column with CHECK constraint instead of a native enum — rejected; the existing column is already `SAEnum(LifecycleStatus, name="registry_lifecycle_status")`; changing the type would be a rewrite.

---

## Decision 6: Decommissioning invisibility via existing filter predicates, not new indexes

**Decision**: Extend the registry's agent-list repository and OpenSearch filter predicates to exclude `decommissioned` wherever `archived` is already excluded. No new indexes needed.

**Rationale**: `list_agents_by_workspace()` in `registry/repository.py` and the OpenSearch marketplace indexer already filter by `LifecycleStatus`; `registry/service.py` at line 324/339 already checks `profile.status is LifecycleStatus.archived` before returning profiles in certain read paths. Adding `decommissioned` to those predicate sets reuses the existing indexing strategy.

**Alternatives considered**: Marketplace index soft-delete flag — rejected; `LifecycleStatus` is already the filter field; introducing a second flag would create two sources of truth.

---

## Decision 7: Instance shutdown delegates to existing `RuntimeControllerClient.StopRuntime`

**Decision**: The `decommission_agent()` service method queries active runtime instances for the agent's FQN, then calls `RuntimeControllerClient.stop_runtime()` for each. The existing Runtime Controller gRPC `StopRuntime` RPC is the shutdown contract.

**Rationale**: Runtime instance lifecycle is owned by the Go Runtime Controller (feature 009). Re-implementing instance shutdown in Python would duplicate state. The decommission method collects active instance IDs for the agent, dispatches `StopRuntime` in parallel, and waits for confirmation (or records the failure and proceeds — in-flight executions allowed to complete per FR-010).

**Alternatives considered**: Publishing a Kafka command for async shutdown — rejected; the decommission audit record must include `active_instance_count_at_decommission` and synchronous shutdown latency is bounded (SC-004, 60s p95).

---

## Decision 8: IBOR pull sync is eventually-consistent, idempotent, partial-success-tolerant

**Decision**: Sync runs are transactional per-user, not per-run. Each directory user is reconciled individually; failures on one user do not abort the run. The overall run status is `succeeded` if all users synced, `partial_success` if any errors occurred but the run completed, `failed` if the run could not start (connector unreachable, credentials invalid).

**Rationale**: A 500-user enterprise tenant will occasionally have individual account mismatches (stale emails, deleted users). Aborting the run on the first failure breaks the idempotency contract and surprises operators. Per-user transaction scope ensures partial success is observable and retryable (FR-017).

**Alternatives considered**: Per-run transaction with full rollback — rejected; operationally rejected by FR-017. Abort on first error — rejected; violates the partial-success contract.

---

## Decision 9: Role-mapping policy is JSONB-serialized, evaluated in connector code

**Decision**: `ibor_connectors.role_mapping_policy` is a JSONB array of rules: `[{"directory_group": "CN=Admins,...", "platform_role": "platform_admin", "workspace_scope": null}, ...]`. Evaluation is first-match-wins, matching the existing `RBACEngine._matches()` semantics.

**Rationale**: Policies are small (typically 10–50 rules), change rarely, and are loaded once per sync run. JSONB is the correct fit (query-free, simple editing, validated by Pydantic at write time). First-match-wins matches the existing RBAC evaluation model so operators do not learn a second ordering rule.

**Alternatives considered**: Separate table for policy rules — rejected; over-engineered for <100 rules per connector. Python module expression — rejected; policies must be operator-editable at runtime.

---

## Decision 10: Sync trigger dispatch — APScheduler for cadence, on-demand via REST

**Decision**: Use `APScheduler` (already a project dependency, feature 022/025/034) to invoke sync runs on the configured cadence. An on-demand REST endpoint (`POST /api/v1/auth/ibor/connectors/{id}/sync`) places a run in a Redis-backed in-progress flag (`ibor:sync:{connector_id}`) to prevent concurrency.

**Rationale**: APScheduler is already the project pattern for periodic work (context-engineering drift monitor, connector framework email poll). Adding a second scheduler would violate Brownfield Rule 4. Redis sliding-window lock for concurrency is the established pattern from policy 028's `MemoryWriteGateService`.

**Alternatives considered**: Kafka-based triggering — rejected; over-engineered; sync is a periodic admin task, not a high-throughput event. `asyncio` background tasks — rejected; lost on pod restart; APScheduler persists schedule state.

---

## Decision 11: Credentials via existing generic S3/secret reference pattern — credential_ref is a pointer

**Decision**: `ibor_connectors.credential_ref` is a Kubernetes Secret name (or equivalent reference). The credential value is resolved at sync time via the existing secrets resolution pattern used by feature 055 (`SECRETS_REF_*`) or the service-account lookup path. Credential values never appear in the connector record and never in any API response.

**Rationale**: FR-016 mandates credential safety. The platform already has a secret-reference convention (feature 009 Runtime Controller, feature 055 prompt preflight). Reusing it avoids a bespoke credential store. REST endpoints that return connector config redact `credential_ref` to the name only.

**Alternatives considered**: Encrypted credential in the DB — rejected; introduces a second secret store. HashiCorp Vault integration — deferred; K8s Secrets are sufficient for the MVP and Vault can layer in without interface change.

---

## Decision 12: Decommission event on existing `registry.events` Kafka topic

**Decision**: Publish `agent_decommissioned` events via a new helper in `registry/events.py` on the existing `registry.events` topic. IBOR sync runs publish `ibor_sync_completed` events on the same topic or on `auth.events` — preferred: `auth.events` since IBOR is auth-bounded.

**Rationale**: Brownfield Rule 4 — use existing topics. `registry.events` already carries `agent_created`, `agent_published`, `agent_deprecated` — adding `agent_decommissioned` continues the pattern. `auth.events` carries existing auth events (login, role changes); IBOR sync events belong there.

**Alternatives considered**: New `ibor.events` topic — rejected; fewer topics is better for operators; `auth.events` is the natural home.

---

## Summary: Genuine Scope (User Plan vs Reality)

| User Plan Step | Status | Actual Scope |
|---|---|---|
| 1. Alembic migration: decommission fields | GENUINE + MORE | Migration 044 adds 3 columns to `registry_agent_profiles`, 1 column to `user_roles`, 1 enum value, 2 new tables (`ibor_connectors`, `ibor_sync_runs`) |
| 2. Create `auth/services/ibor_sync.py` | PATH WRONG | Create `auth/ibor_sync.py` (flat), `auth/ibor_service.py`, extend `auth/repository.py`, `auth/models.py`, `auth/schemas.py`, `auth/router.py` |
| 3. Modify agent model + service | GENUINE + MORE | `registry/models.py` (3 cols + enum), `registry/service.py` (new `decommission_agent()` + list filter), `registry/state_machine.py` (new transitions), `registry/schemas.py` (request/response), `registry/events.py` (new event), `registry/repository.py` (list filter + decommission persistence) |
| 4. Add decommission endpoint | GENUINE | `POST /api/v1/registry/agents/{id}/decommission` in `registry/router.py` |
| 5. Modify rbac_service: IBOR mappings | PATH WRONG | Extend `auth/rbac.py` (`RBACEngine`) to honor `source_connector_id` on `UserRole`; add policy-based role reconciliation helper |
| 6. Write tests | IN SCOPE | 8 new Python test modules (~30 scenarios) |
