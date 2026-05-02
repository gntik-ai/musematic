# Research — UPD-049 Marketplace Scope

**Phase 0 output.** Resolves open questions and documents architectural choices that
underpin the data model, contracts, and tasks.

---

## R1 — Where does the marketplace scope dimension live?

**Decision**: extend `registry_agent_profiles` with two new columns
(`marketplace_scope`, `review_status`) plus four supporting columns (`reviewed_at`,
`reviewed_by_user_id`, `review_notes`, `forked_from_agent_id`). No new table.

**Rationale**:
- Scope is an attribute of an agent, not a separate aggregate. A separate
  `marketplace_listings` table would force a 1:1 join on every read and double the RLS
  surface.
- The existing `registry_agent_profiles` already has every other lifecycle column
  (`status`, `decommissioned_at`, etc.) — colocating the public-review lifecycle is
  consistent.
- A partial index on `(marketplace_scope, review_status)` keeps cross-tenant
  marketplace reads cheap; a separate partial index on `review_status='pending_review'`
  keeps the review queue cheap.

**Alternatives considered**:
- Separate `agent_marketplace_listings` table: rejected — more joins, more RLS, no
  obvious benefit since scope is 1:1 with agent.
- JSONB blob on `registry_agent_profiles`: rejected — defeats the partial-index
  strategy and makes the database CHECK constraint impossible.

---

## R2 — Three-layer Enterprise refusal

**Decision**: refuse public-scope publish from non-default tenants at three layers:
(1) UI scope-picker disabled state with tooltip; (2) application service guard raising
`PublicScopeNotAllowedForEnterpriseError` (HTTP 403); (3) database CHECK constraint
`registry_agent_profiles_public_only_default_tenant` that refuses any row with
`marketplace_scope='public_default_tenant' AND tenant_id <> default_tenant_uuid`.

**Rationale**:
- Defense in depth: a UI-only refusal can be bypassed via API; a service-only refusal
  can be bypassed via direct DB writes (e.g., a buggy migration); the CHECK constraint
  is the last line of defense.
- The default-tenant UUID is a hardcoded constant (seeded by UPD-046 migration 096), so
  the CHECK constraint expression is self-contained and does not require a runtime
  SELECT against `tenants`.
- Each layer is independently testable: the UI test inspects the scope-picker disabled
  state, the API test calls the publish endpoint with a hand-crafted Acme JWT, the DB
  test issues a raw `INSERT ... VALUES (..., 'public_default_tenant', acme_uuid, ...)`.

**Alternatives considered**:
- Service-layer guard only: rejected — direct DB writes (e.g., from migrations,
  database CLI sessions, or future BYPASSRLS code paths) would bypass it.
- Trigger-based refusal: rejected — CHECK constraints are simpler, faster, and
  declaratively visible in `\d+ registry_agent_profiles`.

---

## R3 — Cross-tenant visibility via per-request RLS GUCs

**Decision**: replace the `tenant_isolation` RLS policy on `registry_agent_profiles`
(created by UPD-046 migration 100) with a new `agents_visibility` policy whose USING
expression has three branches:

```sql
tenant_id = current_setting('app.tenant_id', true)::uuid
OR (
    marketplace_scope = 'public_default_tenant'
    AND review_status = 'published'
    AND current_setting('app.tenant_kind', true) = 'default'
)
OR (
    marketplace_scope = 'public_default_tenant'
    AND review_status = 'published'
    AND current_setting('app.consume_public_marketplace', true) = 'true'
)
```

The two new GUCs (`app.tenant_kind`, `app.consume_public_marketplace`) are bound by the
existing SQLAlchemy `before_cursor_execute` listener that already binds `app.tenant_id`
(UPD-046 migration; `apps/control-plane/src/platform/common/database.py`). Both
exception branches require `review_status='published'`, so unapproved drafts never leak.

**Rationale**:
- Per-request GUCs are the canonical PostgreSQL pattern for RLS — they're per-transaction
  via `SET LOCAL`, automatically reset between connection-pool checkouts.
- Two separate exception branches keep the intent visible in the policy expression
  itself (default-tenant users see public; consume-flag tenants see public).
- The `review_status='published'` requirement on both exception branches is the
  invariant that protects FR-021 (unapproved rows never leak).
- Keeping the policy on the same table (instead of moving it to a view) avoids a
  rename of every existing query in `registry/repository.py`.

**Alternatives considered**:
- View-based isolation: rejected — would require touching every existing query.
- Application-layer scope filtering: rejected — RLS gives defense in depth and prevents
  any future bypass via raw SQL.
- Two RLS policies (one for default branch, one for exceptions): rejected — PostgreSQL
  ORs the USING clauses of multiple policies on the same operation, which is functionally
  equivalent but harder to reason about in `\d+`.

---

## R4 — Marketing category list

**Decision**: platform-curated tuple in
`apps/control-plane/src/platform/marketplace/categories.py`:

```python
MARKETING_CATEGORIES = (
    "data-extraction", "summarisation", "code-assistance", "research",
    "automation", "communication", "analytics", "content-generation",
    "translation", "other",
)
```

The Pydantic schema for `MarketingMetadata.category` validates against this constant.
The frontend at `apps/web/lib/marketplace/categories.ts` mirrors the list as a TS
constant. Both files carry a comment cross-referencing each other.

**Rationale**:
- Categories influence search facets, marketing-card layout, and review-queue
  filtering. Treating them as platform-curated (code change, not config change) gives
  auditability — the list cannot drift between regions or environments without a PR.
- The `other` catch-all is intentionally last in the dropdown so the UX reads
  most-specific to most-generic.
- Adding/removing a category does NOT require a migration (it's a Pydantic validation
  change), which keeps the change cost low.

**Alternatives considered**:
- Database-stored category table: rejected — adds a join, adds a sync surface to keep
  in lockstep with the frontend, and allows runtime drift between environments.
- Free-text categories with eventual normalization: rejected — destroys the search
  facet UX and makes the review queue unfilterable.

---

## R5 — Submission rate limiting

**Decision**: Redis sorted set keyed on `marketplace:submission_rate_limit:{user_id}`
with score = epoch milliseconds, value = submission ID. On submit:

1. `ZREMRANGEBYSCORE key 0 (now-24h)` — evict aged-out entries.
2. `ZCARD key` — count remaining.
3. If count >= `MARKETPLACE_SUBMISSION_RATE_LIMIT_PER_DAY` (default 5), refuse with
   `SubmissionRateLimitExceededError` (HTTP 429); compute Retry-After from the oldest
   remaining entry's score.
4. `ZADD key now {submission_id}` — record this submission.
5. `EXPIRE key 86400` — slide the TTL.

**Rationale**:
- Sliding window (per-submitter rolling 24 hours) is the spec requirement, not fixed
  windows.
- Sorted set is the canonical Redis structure for this — O(log N) eviction, O(1) count,
  no Lua script required.
- 5/day is a reasonable default (FR-009) but configurable per
  `MARKETPLACE_SUBMISSION_RATE_LIMIT_PER_DAY` so we can tune from operations without a
  deploy.
- Keying on `user_id` (not `tenant_id`) makes the limiter follow the abuse vector: a
  bot user spinning up submissions is what we're throttling, not "the default tenant
  collectively".
- Fail-closed on Redis outage: if Redis is unreachable, raise an error rather than
  pretending the submission succeeded; the publish flow is not so urgent that it must
  proceed during a Redis outage.

**Alternatives considered**:
- Fixed-window counters: rejected — bursty around window boundaries.
- PostgreSQL-row-counted limit: rejected — adds load to the primary write path,
  doesn't slide cleanly.
- Token bucket in memory per process: rejected — no cross-process coordination.

---

## R6 — Review-queue claim semantics

**Decision**: optimistic conditional update. `claim` runs:

```sql
UPDATE registry_agent_profiles
   SET reviewed_by_user_id = :reviewer_id
 WHERE id = :agent_id
   AND review_status = 'pending_review'
   AND (reviewed_by_user_id IS NULL OR reviewed_by_user_id = :reviewer_id)
RETURNING reviewed_by_user_id
```

If `RETURNING` is empty, fetch the row's current `reviewed_by_user_id`. If it's a
different reviewer, raise `ReviewAlreadyClaimedError` (HTTP 409). Otherwise raise
`SubmissionAlreadyResolvedError` (HTTP 409). Re-claiming by the same reviewer is a
no-op success (idempotent per FR-014).

**Rationale**:
- A single conditional UPDATE is atomic without distributed locking.
- The claim is essentially a soft lock with no expiry — reviewers must explicitly
  release. Aged-out claims are an operational concern (super admin can release on
  behalf of a stuck reviewer).
- Idempotence on same reviewer simplifies UI (re-clicking "Claim" doesn't error).

**Alternatives considered**:
- Distributed lock via Redis with TTL: rejected — over-engineered for a low-volume
  human action; a Redis outage shouldn't break review claims.
- Pessimistic SELECT FOR UPDATE: rejected — holds a row lock for the duration of the
  HTTP request, which can cause contention if the reviewer's session takes minutes.

---

## R7 — Fork semantics: shallow copy with provenance

**Decision**: a fork creates a NEW `registry_agent_profile` row in the consumer's
tenant with:

- A fresh `id` (new UUID)
- `tenant_id` = consumer's tenant
- `workspace_id` = consumer-chosen workspace (or default workspace for tenant scope)
- `namespace_id` = consumer-chosen namespace
- `local_name` = consumer-chosen name (validated against existing FQN-uniqueness
  constraint)
- `marketplace_scope` = consumer-chosen (`workspace` or `tenant` — never
  `public_default_tenant`)
- `review_status` = `draft`
- `forked_from_agent_id` = source agent's `id`
- All operational fields (prompts, capability declarations, tool dependencies,
  behaviour metadata) — copied
- All review fields (`reviewed_at`, `reviewed_by_user_id`, `review_notes`) — NULL
- Marketing metadata — NOT copied (forks are private)

The source agent is unchanged. The fork's revisions are NOT copied; the fork starts a
fresh revision lineage at v1.

Tool dependencies that are not registered in the consumer's tenant are surfaced via a
`tool_dependencies_missing` warning array in the fork response — the fork still
succeeds (the tools can be registered later).

**Rationale**:
- Shallow copy is the simplest model that satisfies FR-024 and FR-025.
- Resetting `review_status` to `draft` makes intent explicit: a fork is private until
  the owner explicitly publishes it (and re-enters review if they pick public scope).
- Preserving `forked_from_agent_id` enables the source-update notification fan-out
  (FR-027) and gives source creators an "adoption" view.
- Not copying revisions keeps the operation O(1) and avoids implying that the fork
  inherits future upstream revisions.

**Alternatives considered**:
- Deep copy with revisions: rejected — changes the semantics from "fork" to "branch",
  surfaces upstream history that the consumer didn't author, and balloons storage.
- Symbolic link to source: rejected — the spec explicitly requires consumer-side
  edits be private to the consumer, which a symbolic link would prevent.

---

## R8 — Source-updated notification fan-out

**Decision**: when a public source agent's update is approved (`review_status` →
`published` after a re-review), the registry service publishes
`marketplace.source_updated` with the source agent's `id`. A new
`apps/control-plane/src/platform/marketplace/notifications.py` consumer (subscribed to
the `marketplace.events` topic) finds all `registry_agent_profiles` rows with
`forked_from_agent_id = source_id` and calls the existing `AlertService` (UPD-042) to
deliver one alert per fork to the fork's owner. The alert body names the source FQN,
the new version, the diff hash, and the explicit statement "this fork has NOT been
auto-updated".

The fan-out is gated by `MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS` (default `true`).

**Rationale**:
- Reuses UPD-042's notification path — no new delivery surface.
- The fan-out runs on a separate consumer to keep the publish-with-scope hot path
  fast; if the fan-out is slow or fails, the publish itself is unaffected.
- The "diff summary hash" is just an SHA-256 of the new revision's package SHA — we
  intentionally do NOT compute a semantic diff (LLM-generated change summary), since
  that's expensive and the consumer can click through to compare versions if they
  want detail.

**Alternatives considered**:
- Synchronous fan-out inside the publish handler: rejected — couples publish latency
  to the fan-out throughput.
- Subscribe-based "watching" model where forks explicitly opt in: rejected — defeats
  the safety purpose (the whole point is that forks should know when their upstream
  changed, even if they forgot to opt in).

---

## R9 — Migration ordering

**Decision**: a single Alembic migration `108_marketplace_scope_and_review.py` that
runs steps in this order:

1. `ALTER TABLE registry_agent_profiles ADD COLUMN marketplace_scope ...` (with
   server_default `'workspace'` and CHECK constraint).
2. `ALTER TABLE registry_agent_profiles ADD COLUMN review_status ...` (with
   server_default `'draft'` and CHECK constraint).
3. `ALTER TABLE registry_agent_profiles ADD COLUMN reviewed_at ...`,
   `reviewed_by_user_id ...` (FK to `users.id` ON DELETE SET NULL),
   `review_notes ...`, `forked_from_agent_id ...` (self-FK ON DELETE SET NULL).
4. Two partial indexes: review queue (`WHERE review_status='pending_review'`) and
   public-marketplace (`WHERE marketplace_scope='public_default_tenant' AND
   review_status='published'`).
5. The three-layer-refusal CHECK constraint
   `registry_agent_profiles_public_only_default_tenant`.
6. `DROP POLICY tenant_isolation ON registry_agent_profiles`.
7. `CREATE POLICY agents_visibility ON registry_agent_profiles ...` per the expression
   in R3.
8. `ALTER TABLE registry_agent_profiles FORCE ROW LEVEL SECURITY` (idempotent — already
   set by migration 100; explicit for clarity).

The reverse migration runs the steps in reverse order: drop the new policy, restore
`tenant_isolation`, drop the CHECK constraints, drop the indexes, drop the columns.

**Rationale**:
- Single migration keeps the change atomic from operations' point of view.
- The policy-replacement is the "scary" step; doing it last (after columns, indexes,
  and CHECKs are in place) means the policy replacement has all the metadata it
  references already in the schema.
- All `ADD COLUMN` operations have server defaults so they are O(1) on PostgreSQL 16
  (no full-table rewrite).

**Alternatives considered**:
- Multiple migrations (one per concern): rejected — overkill, and each migration would
  need its own up/down.
- Online migration tool (pg-osc, Soundcloud's lhm): rejected — not needed because all
  the column adds are O(1).

---

## R10 — `consume_public_marketplace` setter audit semantics

**Decision**: extend `TenantsService` with `set_feature_flag(tenant_id, flag_name,
value, super_admin_id)`. The method validates:

- `flag_name` is in a documented allowlist (currently just `consume_public_marketplace`).
- The tenant `kind` is compatible with the flag (`consume_public_marketplace` requires
  `kind='enterprise'` — refused on default tenant since the flag is meaningless there;
  the default tenant already sees public listings as the publisher).

It then:

1. Updates the tenant's `feature_flags` JSONB column.
2. Records a hash-linked audit-chain entry whose payload includes both the old and new
   values.
3. Publishes a `tenants.feature_flag_changed` Kafka event on the existing
   `tenants.lifecycle` topic.
4. Invalidates the tenant resolver cache for that tenant so the next request picks up
   the new flag.

**Rationale**:
- Reuses the existing `tenants.lifecycle` Kafka topic (already wired in by UPD-046)
  rather than creating a new topic for flag changes.
- The audit chain entry, the event payload, and the resolver cache invalidation are
  the same three side effects every other tenant lifecycle action takes — symmetric,
  predictable, easy to test.
- Refusing the flag on the default tenant is a soft guard (the constraint is logical,
  not legal — you could imagine a future flag that's default-tenant-only), but for
  this specific flag it would be confusing UX.

**Alternatives considered**:
- A generic per-tenant flag-management API: rejected — premature; we have one flag,
  ship it, generalize when we have three.
- Storing the flag in a separate `tenant_feature_flags` table: rejected — `tenants`
  already carries `feature_flags` JSONB.
