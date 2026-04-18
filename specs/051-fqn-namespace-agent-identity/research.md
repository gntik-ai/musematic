# Research: FQN Namespace System and Agent Identity

**Feature**: 051-fqn-namespace-agent-identity
**Phase**: 0 — Research
**Date**: 2026-04-18

---

## Decision 1: What Already Exists vs. What Needs to Be Added

**Decision**: The core FQN system is already implemented in the initial backlog (feature 021 — Agent Registry & Ingest). The update pass adds only the three genuine gaps.

**Already implemented** (cite: `apps/control-plane/src/platform/registry/models.py`):
- `registry_namespaces` table as `AgentNamespace` model (workspace_id, name, description, created_by, UUIDMixin, TimestampMixin)
- `fqn` field on `AgentProfile` — `String(127)`, unique index, format `namespace:local_name`
- `namespace_id` FK and `local_name` on `AgentProfile` with `UniqueConstraint(namespace_id, local_name)`
- `visibility_agents`, `visibility_tools` — JSONB lists of FQN patterns on `AgentProfile`
- `purpose`, `approach` — text fields on `AgentProfile`
- `role_types` — JSONB list using `AgentRoleType` enum (executor, planner, orchestrator, observer, judge, enforcer, custom)

**Already implemented** (cite: `apps/control-plane/src/platform/registry/router.py`):
- `POST /api/v1/namespaces`, `GET /api/v1/namespaces`, `DELETE /api/v1/namespaces/{namespace_id}`
- `GET /api/v1/agents/resolve/{fqn}` — exact FQN resolution
- `GET /api/v1/agents?fqn_pattern=...` — FQN pattern discovery
- `PATCH /api/v1/agents/{agent_id}` — including visibility fields

**Already implemented** (cite: `apps/control-plane/src/platform/registry/service.py`):
- `resolve_effective_visibility()` — unions per-agent and workspace-level visibility patterns

**Three genuine gaps to implement**:
1. `agent_fqn` absent from `CorrelationContext` in `apps/control-plane/src/platform/common/events/envelope.py`
2. Purpose `min_length` is `10` in `AgentManifest` schema; spec requires `50`
3. No backfill migration for agents created before FQN system (next migration: `041_fqn_backfill.py`)

**Rationale**: Brownfield rule 1 (never rewrite) — the existing implementation is correct and complete for the core FQN feature. The update pass extends only what is truly missing.

**Alternatives considered**:
- Treating this as a full new implementation: Violates Brownfield Rule 1. The 021 feature already shipped the namespace + FQN system.

---

## Decision 2: Event Envelope Extension — Optional Field, Additive

**Decision**: Add `agent_fqn: str | None = None` to `CorrelationContext` in `apps/control-plane/src/platform/common/events/envelope.py`.

**Rationale**: Brownfield Rule 7 (backward-compatible APIs). Making `agent_fqn` optional with default `None` means all existing event producers continue to work without changes. New producers that know the agent FQN set it explicitly. Downstream consumers (analytics, agentops, monitoring) read it if present, ignore it if absent.

**Alternatives considered**:
- Required field: Breaks all existing event publishers that don't set it. Violates backward compatibility.
- Separate FQN envelope wrapper: Unnecessary complexity. A single optional field on `CorrelationContext` is the right scope.

---

## Decision 3: Purpose Validation Change — Schema Update to min_length=50

**Decision**: Update `AgentManifest.purpose` field in `apps/control-plane/src/platform/registry/schemas.py` from `min_length=10` to `min_length=50`.

**Rationale**: The spec (FR-007) requires 50-character minimum for meaningful purpose statements. The existing `min_length=10` was a placeholder. This is a breaking change for any agent manifest with 10–49 character purpose fields. The backfill migration (Decision 4) flags these for manual review rather than rejecting them.

**Brownfield safety**: The `AgentManifest` schema is used for package upload validation (`POST /api/v1/agents/upload`). Changing the validator only affects new uploads and updates — it does not retroactively invalidate existing agents. The `AgentPatch` schema does not currently validate purpose length; it should be updated consistently.

**Alternatives considered**:
- Keeping `min_length=10`: Does not meet spec requirement FR-007. Purpose is meaningless for trust evaluation at 10 characters.
- Enforcing 50 retroactively: Would require invalidating existing agents. Not appropriate for brownfield.

---

## Decision 4: Backfill Migration — Idempotent, Workspace-Scoped Default Namespace

**Decision**: Create migration `041_fqn_backfill.py` that:
1. For each workspace that has agents without `namespace_id`: creates a namespace named `"default"` (using `INSERT ... ON CONFLICT DO NOTHING` for idempotency)
2. Sets `namespace_id` and `local_name` on all agents where `namespace_id IS NULL`, deriving `local_name` from the existing `name` or `display_name` field (slugified: lowercase, spaces→hyphens, strip invalid chars)
3. Populates `fqn = 'default:' || local_name` for those agents
4. Sets `purpose = description` where `purpose = ''` AND `description IS NOT NULL`, flags with a `needs_reindex = true` marker if `length(purpose) < 50`
5. Runs entirely in the `upgrade()` function of the Alembic migration; `downgrade()` does nothing (data migration is one-way)

**Rationale**: Brownfield Rule 2 (Alembic-only DDL/data changes). Idempotency ensures safe re-runs. Using `ON CONFLICT DO NOTHING` for the default namespace creation prevents duplicate namespace errors if the migration is run twice.

**Alternatives considered**:
- Python management command: Not idempotent by default, not tracked by Alembic migration chain.
- Running backfill in application startup code: Couples data migration to app lifecycle; runs on every pod restart.

---

## Decision 5: FQN Pattern Syntax — Existing SQL LIKE + Glob Implementation Sufficient

**Decision**: No changes needed to the FQN pattern matching implementation. The existing `repository.py` already implements FQN pattern matching using SQL LIKE predicates (converting `*` wildcards to `%` for SQL LIKE) with workspace scoping.

**Cite**: `apps/control-plane/src/platform/registry/repository.py` — `_build_visibility_predicate()` and `list_agents()` with `fqn_pattern` filter.

**Rationale**: The spec (FR-005) requires patterns like `finance-ops:*` and `*:kyc-*`. The existing implementation converts glob `*` to SQL `%` which handles both cases. No new pattern syntax is needed.

**Alternatives considered**:
- Regex-based matching: More powerful but slower and harder to index. LIKE patterns are indexed via PostgreSQL trigrams if a GIN index exists.

---

## Decision 6: role_type vs. role_types — Single vs. Multi-Value

**Decision**: Keep the existing `role_types` JSONB list (multi-valued) rather than introducing a single `role_type` column. The spec says "role type classification" without specifying cardinality, and the existing model supports multiple role types per agent.

**Rationale**: The existing `AgentRoleType` enum has 6 values (executor, planner, orchestrator, observer, judge, enforcer, custom). Agents can have multiple roles (e.g., both "judge" and "observer"). Changing to single-value would require a breaking migration and would lose expressiveness.

**Impact on spec**: FR-009 says "valid role types: executor, observer, judge, enforcer, coordinator, planner" and "default: executor". The existing enum has `orchestrator` instead of `coordinator`. These are functionally equivalent names. No change needed — `orchestrator` is the existing term for what the spec calls `coordinator`.

**Alternatives considered**:
- Adding a `role_type` single-value column: Redundant. The JSONB `role_types` already serves this purpose more flexibly.

---

## Decision 7: OpenSearch Index Mapping for Purpose Full-Text Search

**Decision**: The existing `agent_catalog` OpenSearch index already indexes `purpose` as a `text` field (mapped during 021 feature setup). No new mapping update is needed. The backfill migration sets `needs_reindex = true` for agents whose purpose is updated, triggering the existing async re-indexing worker.

**Rationale**: The 021 feature already includes OpenSearch integration with purpose indexing. The `needs_reindex` flag on `AgentProfile` triggers the existing background embedding/indexing task in `RegistryService`.

**Alternatives considered**:
- Manual re-indexing script: Already handled by the existing `needs_reindex` flag mechanism. No new script needed.
