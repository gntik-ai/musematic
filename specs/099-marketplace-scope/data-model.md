# Data Model — UPD-049 Marketplace Scope

**Phase 1 output.** Documents the additive schema changes the migration applies and the
resulting entity relationships.

---

## Table changes

UPD-049 is **additive** — no new tables, no dropped columns, no renamed columns.
All changes target the existing `registry_agent_profiles` table.

### `registry_agent_profiles` (extended)

Existing columns are unchanged. New columns:

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `marketplace_scope` | `VARCHAR(32)` | NO | `'workspace'` | CHECK ∈ {`workspace`, `tenant`, `public_default_tenant`}. CHECK `marketplace_scope <> 'public_default_tenant' OR tenant_id = '00000000-0000-0000-0000-000000000001'::uuid` (three-layer Enterprise refusal — DB layer). |
| `review_status` | `VARCHAR(32)` | NO | `'draft'` | CHECK ∈ {`draft`, `pending_review`, `approved`, `rejected`, `published`, `deprecated`}. |
| `reviewed_at` | `TIMESTAMPTZ` | YES | NULL | Set on approve/reject. |
| `reviewed_by_user_id` | `UUID` | YES | NULL | FK `users.id ON DELETE SET NULL`. Doubles as the claim marker (set on claim, cleared on release). |
| `review_notes` | `TEXT` | YES | NULL | Reviewer's notes (approval optional, rejection required). |
| `forked_from_agent_id` | `UUID` | YES | NULL | FK `registry_agent_profiles.id ON DELETE SET NULL`. NULL for non-forked agents. |

### Partial indexes

| Index | Columns | Predicate | Purpose |
|---|---|---|---|
| `registry_agent_profiles_review_status_idx` | `(review_status)` | `WHERE review_status = 'pending_review'` | Cheap review-queue scans (typically <100 rows). |
| `registry_agent_profiles_scope_status_idx` | `(marketplace_scope, review_status)` | `WHERE marketplace_scope = 'public_default_tenant' AND review_status = 'published'` | Cheap public-marketplace listing reads cross-tenant. |

### CHECK constraints

| Constraint | Expression |
|---|---|
| `registry_agent_profiles_marketplace_scope_check` | `marketplace_scope IN ('workspace', 'tenant', 'public_default_tenant')` |
| `registry_agent_profiles_review_status_check` | `review_status IN ('draft', 'pending_review', 'approved', 'rejected', 'published', 'deprecated')` |
| `registry_agent_profiles_public_only_default_tenant` | `marketplace_scope <> 'public_default_tenant' OR tenant_id = '00000000-0000-0000-0000-000000000001'::uuid` |

### Foreign keys

| FK | Target | ON DELETE |
|---|---|---|
| `reviewed_by_user_id` | `users.id` | SET NULL |
| `forked_from_agent_id` | `registry_agent_profiles.id` (self) | SET NULL |

---

## RLS policy replacement

**Migration 108 step 4**: drop `tenant_isolation` (created by UPD-046 migration 100) on
`registry_agent_profiles` and create `agents_visibility`:

```sql
CREATE POLICY agents_visibility ON registry_agent_profiles
USING (
    -- default branch: tenant isolation
    tenant_id = current_setting('app.tenant_id', true)::uuid
    -- exception 1: default-tenant users see public-published agents
    OR (
        marketplace_scope = 'public_default_tenant'
        AND review_status = 'published'
        AND current_setting('app.tenant_kind', true) = 'default'
    )
    -- exception 2: consume-flag-set tenants see public-published agents
    OR (
        marketplace_scope = 'public_default_tenant'
        AND review_status = 'published'
        AND current_setting('app.consume_public_marketplace', true) = 'true'
    )
);
```

Both exceptions require `review_status = 'published'`, so unapproved drafts never
leak. The `app.tenant_kind` and `app.consume_public_marketplace` GUCs are bound by the
existing SQLAlchemy `before_cursor_execute` listener at
`apps/control-plane/src/platform/common/database.py` (extended by T012 in `tasks.md`).

---

## Review-status state machine

```text
                    submit (public scope only)
                  ┌────────────────────────────┐
                  │                            ▼
   ┌────────┐     │          ┌──────────────────────┐
   │ draft  │ ────┘          │   pending_review     │
   └───┬────┘                └─┬──────────────┬─────┘
       │ publish               │ approve      │ reject
       │ (workspace            ▼              ▼
       │  /tenant)        ┌─────────┐    ┌──────────┐
       │                  │ approved│    │ rejected │
       │                  └────┬────┘    └──────────┘
       │                       │ publish (auto on approve for public)
       ▼                       ▼
   ┌────────┐         ┌─────────────┐         ┌─────────────┐
   │ workspace/│      │  published  │ ───────►│ deprecated  │
   │ tenant   │      └─────────────┘ deprecate└─────────────┘
   │ published│
   └────────┘
```

Transitions:

- `draft → pending_review` — submitter calls `POST /publish` with
  `scope=public_default_tenant`. Records `marketplace.submitted`.
- `pending_review → published` — reviewer approves. Records `marketplace.approved` then
  `marketplace.published`.
- `pending_review → rejected` — reviewer rejects with reason. Records
  `marketplace.rejected`. Notification delivered.
- `draft → published` — submitter calls `POST /publish` with `scope=workspace` or
  `scope=tenant`. Bypasses review (no public visibility). Records
  `marketplace.published`.
- `published → deprecated` — owner calls `POST /deprecate-listing`. Records
  `marketplace.deprecated`.
- `rejected → pending_review` — submitter resubmits (treated as a new submission, rate
  limit applies).

---

## Marketplace-scope state machine

```text
   ┌──────────┐  promote   ┌────────┐  promote*  ┌────────────────────┐
   │workspace │ ─────────► │ tenant │ ─────────► │public_default_tenant│
   └──────────┘            └────────┘            └────────────────────┘
        ▲                       │                          │
        └───────────────────────┴──────────────────────────┘
                          demote (scope-change)

   * promote to public_default_tenant requires:
     - the tenant is the default tenant (FR-006/011/012 — three-layer refusal)
     - marketing metadata is provided (FR-005)
     - submission rate limit not exceeded (FR-009)
     - review queue acceptance (FR-016)
```

Transitions are recorded by `POST /api/v1/registry/agents/{id}/marketplace-scope`
(scope change without publish) or `POST /api/v1/registry/agents/{id}/publish` (scope
change combined with state-machine transition). Scope changes record an
`marketplace.scope_changed` event.

---

## Entity relationships

```text
tenants                                 users
  │                                       │
  │ (FK tenant_id, RLS-isolated)          │ (FK reviewed_by_user_id, ON DELETE SET NULL)
  ▼                                       ▼
registry_agent_profiles ─────────────────►registry_agent_profiles (self-FK forked_from_agent_id)
  │
  │ (FK agent_profile_id, cascade)
  ▼
registry_agent_revisions
  │
  ▼
registry_lifecycle_audit (existing)
```

**Existing relationships unchanged**: `registry_agent_profiles` →
`registry_agent_revisions`, `registry_lifecycle_audit`, `registry_namespaces`,
`workspaces`, `tenants` are all preserved.

**New self-FK**: `forked_from_agent_id` references `registry_agent_profiles.id` and
allows efficient "find all forks of source X" queries via
`WHERE forked_from_agent_id = :source_id` (with the existing index on `id` as a PK
serving as the inner-loop driver).

---

## Frontend type mirroring

The frontend mirrors backend types in `apps/web/lib/marketplace/types.ts` (TypeScript
interfaces matching the Pydantic schemas) and `apps/web/lib/marketplace/categories.ts`
(TS const tuple matching `MARKETING_CATEGORIES`). T091 in `tasks.md` enforces that the
two stay in lockstep via a CI check (`pnpm test:marketplace-types`).

---

## Audit-chain payload schema

Every state transition records an audit-chain entry via the existing
`AuditChainService.append`. The payload includes:

```jsonc
{
  "agent_id": "uuid",
  "from_state": { "marketplace_scope": "workspace", "review_status": "draft" },
  "to_state":   { "marketplace_scope": "public_default_tenant", "review_status": "pending_review" },
  "actor_user_id": "uuid",
  "reason": "...",            // for reject and deprecate
  "marketing_metadata_hash": "sha256-..."  // for submit
}
```

The chain hash includes the tenant_id per UPD-046 R7 — cross-tenant audit chains stay
correctly partitioned.
