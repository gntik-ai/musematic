# Research: GID Correlation and Event Envelope Extension

**Feature**: 052-gid-correlation-envelope
**Phase**: 0 — Research
**Date**: 2026-04-18

---

## Decision 1: `goal_id` already exists on the event envelope — no field addition needed

**Decision**: Do not add `goal_id` to `CorrelationContext`. It is already present (see `apps/control-plane/src/platform/common/events/envelope.py:16`).

**Rationale**: A file grep confirms `goal_id: UUID | None = None` is already defined on `CorrelationContext`, shipped with feature 018 (Workspaces) and 024 (Interactions). Goal payload models (`GoalMessagePostedPayload`, `GoalStatusChangedPayload`, `InteractionStartedPayload`, `AttentionRequestedPayload.related_goal_id`) also already carry `goal_id` in their bodies. The user's plan step "add goal_id to CorrelationContext" is therefore a no-op.

**Alternatives considered**: Duplicating the field under a different name (rejected — would break Principle X "GID is a first-class correlation dimension" which already names the field `goal_id`).

---

## Decision 2: `X-Goal-Id` HTTP header extraction via the existing correlation middleware

**Decision**: Extend `CorrelationMiddleware` in `apps/control-plane/src/platform/common/correlation.py` to extract `X-Goal-Id`, validate it as a UUID, bind it to a new `goal_id_var: ContextVar[str]`, attach it to `request.state.goal_id`, and echo it on the response. If the header is present but not a valid UUID, return HTTP 422 without invoking the downstream handler.

**Rationale**: The existing middleware already implements the same pattern for `X-Correlation-ID` (context var + `request.state` + echoed header). Following the established pattern satisfies Brownfield Rule 4 (use existing patterns) and keeps the propagation surface tiny.

**Alternatives considered**:
- A separate middleware for goal extraction (rejected — adds a stack frame with no benefit and violates "use existing patterns").
- Accept arbitrary strings instead of UUIDs (rejected — `goal_id` is a UUID everywhere else; accepting strings invites malformed data to leak into analytics).

---

## Decision 3: Envelope auto-population from the request-scoped `goal_id_var`

**Decision**: Extend `make_envelope(...)` in `envelope.py` with an optional `goal_id: UUID | None = None` keyword. When `correlation_context` is `None`, read the ContextVar fallback (`goal_id_var.get()`) in addition to `agent_fqn`. When `correlation_context` is provided and `goal_id` is `None` on the context, fall back to the ContextVar. Explicit values on the caller-supplied context always win.

**Rationale**: Mirrors the existing `agent_fqn` parameter pattern introduced in feature 051 (`make_envelope(..., agent_fqn=...)`). This means any event produced inside an HTTP request context that included `X-Goal-Id` automatically carries `goal_id` without each router having to pass it explicitly — satisfying FR-004 at the lowest possible implementation cost.

**Alternatives considered**:
- Retrofit every router and service call site to read `request.state.goal_id` and pass it into `_correlation(...)`/`make_envelope(...)` explicitly (rejected — high blast radius across ~20 bounded contexts; touches files this feature has no reason to modify; violates Brownfield Rule 1 spirit).
- Do nothing at the envelope layer and require callers to pass `goal_id` (rejected — leaves FR-004 unmet; operators will see chains that start with GID at the edge and drop it at the first event).

---

## Decision 4: `post_goal_message` already sets `goal_id` on the envelope — no change needed for that path

**Decision**: Leave `InteractionService.post_goal_message` unchanged.

**Rationale**: A grep shows `post_goal_message` already invokes `self._correlation(workspace_id=workspace_id, goal_id=goal_id)` when publishing `GoalMessagePostedPayload` (`apps/control-plane/src/platform/interactions/service.py:431`). The `_correlation` helper accepts `goal_id` and populates it on `CorrelationContext`. The spec's US4 is therefore already satisfied for the goal-message path. The user's input mentioned `workspace_goal_service.py` — that path does not exist; `post_goal_message` in `interactions/service.py` is its factual equivalent.

**Alternatives considered**: None — observed code already meets the requirement.

---

## Decision 5: Other goal-emitting service paths — audit rather than blanket-modify

**Decision**: Audit `publish_goal_status_changed` and `publish_attention_requested` (for attention requests with `related_goal_id`) call sites. If they do not currently set `goal_id` on the envelope correlation context, fix them by passing `goal_id` to `self._correlation(...)`. Do not touch unrelated paths.

**Rationale**: Minimising modified files per Brownfield Rule 5 ("Reference existing files"). The spec's US4 targets producers that act on behalf of a goal; only a small number of call sites in `interactions/service.py` are candidates.

**Alternatives considered**: Retrofit every bounded context to carry `goal_id` (rejected — see Decision 3; the envelope auto-population via ContextVar removes the need for per-caller changes).

---

## Decision 6: ClickHouse schema extension follows the existing `deploy/clickhouse/init/` convention, not Alembic

**Decision**: Add a new numbered init SQL file `deploy/clickhouse/init/007-add-goal-id.sql` that (a) `ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID)`, (b) `ALTER TABLE usage_hourly ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID)`, (c) re-creates `usage_hourly_mv` to include `goal_id` in SELECT and GROUP BY. Include `IF NOT EXISTS` / `IF EXISTS` clauses for idempotency.

**Rationale**: ClickHouse schema in this codebase is managed by idempotent init SQL files under `deploy/clickhouse/init/` (files 001–006). Alembic is PostgreSQL-only. Brownfield Rule 2 ("Every change is an Alembic migration") applies to PostgreSQL schema; ClickHouse schema follows its own analogous versioning convention in the init directory. Re-running the init script is safe because of `IF (NOT) EXISTS` guards.

**Alternatives considered**:
- Put the DDL inline in the analytics bootstrap code (rejected — loses the numbered-file audit trail; makes rollback harder).
- Create a stand-alone Alembic migration (rejected — Alembic's metadata doesn't reach ClickHouse; the change would fail to apply).

**Note on downtime**: `ALTER TABLE ... ADD COLUMN Nullable(UUID)` on a ClickHouse `MergeTree` is a metadata-only change and does not rewrite data; it is safe to run online.

---

## Decision 7: Update the materialized view and its target table, not only the base table

**Decision**: In the same ClickHouse init SQL, (a) `ALTER TABLE usage_hourly ADD COLUMN IF NOT EXISTS goal_id Nullable(UUID)`, (b) `DROP VIEW IF EXISTS usage_hourly_mv`, (c) `CREATE MATERIALIZED VIEW usage_hourly_mv TO usage_hourly AS ...` with `goal_id` added to the `SELECT` projection and `GROUP BY`, (d) update `ORDER BY` on `usage_hourly` to include `goal_id` (requires recreating the target table in a controlled way — see below).

**Rationale**: A materialized view that writes to `usage_hourly` must carry `goal_id` end-to-end or the aggregate simply won't include the new dimension. `SummingMergeTree`'s summing behavior requires the new column to appear in both the base MV SELECT and the target ORDER BY for correct aggregation.

**Safe path for `ORDER BY` change**: Because changing `ORDER BY` on a `SummingMergeTree` is not supported by `ALTER`, the migration creates a new target table `usage_hourly_v2` with `goal_id` in `ORDER BY`, redirects the MV to it, and retains `usage_hourly` as a renamed historical table for backward-compatibility of existing queries. The analytics repository reads from both and unions the results during the transition window. Mark this strategy in the plan; the exact execution can be deferred to the tasks phase.

**Alternatives considered**:
- Skip updating the MV and keep per-goal aggregation in the base table only (rejected — every per-goal query then scans the raw `usage_events` partition, killing SC-003 performance targets).
- Recreate the MV in-place with no migration of aggregated data (rejected — loses historical aggregates; we'd have to backfill from raw events).

---

## Decision 8: Analytics consumer extracts `goal_id` from the correlation context (not from payload)

**Decision**: In `apps/control-plane/src/platform/analytics/consumer.py::AnalyticsPipelineConsumer._extract_usage_event` and `._extract_quality_event`, add `"goal_id": envelope.correlation_context.goal_id,` to the returned dict. Update `AnalyticsRepository.insert_usage_events_batch` (and its quality counterpart) to include the new column in its `INSERT` statement column list.

**Rationale**: The authoritative source is the envelope's `correlation_context.goal_id`, populated by Decision 3 (auto-propagation). Reading from the payload would be fragile because the goal may not appear in every event type's payload schema, and would duplicate truth.

**Alternatives considered**: Pull `goal_id` from the payload as a secondary fallback (rejected — the envelope is the canonical location; if it's empty there, the event was produced outside a goal context and `goal_id` should be NULL).

---

## Decision 9: OpenSearch log index mapping extension — update `audit-events` template and let rollover pick it up

**Decision**: Extend `deploy/opensearch/init/init_opensearch.py::create_index_templates.audit_template.mappings.properties` to include `goal_id: {"type": "keyword"}`. Similarly add `goal_id` to `connector-payloads` template (optional but cheap for symmetry; connector deliveries may be goal-scoped).

**Rationale**: OpenSearch index templates in this codebase are defined in Python (not YAML); updating the dict and re-running the init job is the established mechanism. New indexes rolled over via ISM will pick up the new mapping; existing indexes retain their old mapping but accept the new field as dynamic mapping (OpenSearch default) so no backfill is needed.

**Alternatives considered**:
- Add a full new template `platform-logs-*` dedicated to structured app logs (rejected — that template does not exist yet; out of scope for this feature. The constitution's data-stores table mentions `execution_logs` but no such template is wired in the current codebase).
- Force-recreate existing indexes (rejected — destructive, violates Brownfield Rule 1, and unnecessary because OpenSearch dynamic mapping makes `goal_id` filterable from its first appearance in the index).

---

## Decision 10: Backward compatibility and rollout

**Decision**: All changes are additive and backward-compatible. Events without `goal_id` continue to deserialize (Pydantic default `None`). Analytics rows without `goal_id` appear as `NULL` and are filtered cleanly by any query that applies a `goal_id =` predicate. Log documents without `goal_id` are simply excluded from `goal_id` filter queries.

**Rationale**: Satisfies Brownfield Rule 7 (backward-compatible APIs) and FR-007/FR-013 in the spec. No feature flag is required because the change does not alter default behavior — it only exposes a new optional dimension.

**Alternatives considered**: Feature flag the envelope auto-propagation (rejected — no negative consequence to setting a field that consumers already tolerate being `None`).

---

## Summary table

| Area | Change | File(s) |
|------|--------|---------|
| Envelope field | NONE (already shipped) | `common/events/envelope.py` |
| Envelope auto-propagation | NEW | `common/events/envelope.py` (extend `make_envelope`) |
| HTTP middleware | NEW | `common/correlation.py` (new ContextVar + header extraction + validation + echo) |
| Internal producer (goal message) | NONE (already correct) | `interactions/service.py::post_goal_message` |
| Internal producer (goal status, attention) | Audit + small fix if missing | `interactions/service.py` |
| Analytics consumer | Extend extraction + INSERT | `analytics/consumer.py`, `analytics/repository.py` |
| ClickHouse schema | ADD column + recreate MV | `deploy/clickhouse/init/007-add-goal-id.sql` (NEW) |
| OpenSearch mapping | Extend audit/connector templates | `deploy/opensearch/init/init_opensearch.py` |
| Tests | Unit + integration | `tests/unit/common/test_correlation.py`, `tests/unit/common/test_envelope.py`, `tests/unit/test_analytics_consumer.py`, `tests/integration/test_opensearch_init.py` |
