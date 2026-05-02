# Marketplace Scope (UPD-049)

UPD-049 introduces a **marketplace scope dimension** on every published agent
plus a per-Enterprise-tenant feature flag that lets tenants opt in to the
public marketplace. This page covers the three scopes, the platform-staff
review queue, the fork operation, and the operator surface for the
`consume_public_marketplace` flag.

> Spec: [`specs/099-marketplace-scope/spec.md`](../../specs/099-marketplace-scope/spec.md)
>
> Architecture decision record: see also
> [`docs/saas/tenant-architecture.md`](./tenant-architecture.md) for the
> hub-and-spoke tenant model that this feature builds on.

---

## The three scopes

| Scope | Visibility |
|---|---|
| `workspace` (default) | Only the workspace where the agent was published. |
| `tenant` | Every workspace inside the publishing tenant. |
| `public_default_tenant` | Every default-tenant user **plus** Enterprise tenants whose `consume_public_marketplace` flag is set. |

Public publishing is **reserved to the default tenant**. An Enterprise
tenant cannot expose its agents publicly; it can only consume the public
hub. This is enforced in three layers (FR-010 / FR-011 / FR-012):

1. **UI** — the publish flow's scope picker disables the public option
   for Enterprise tenants and surfaces a tooltip.
2. **Service** — `RegistryService.publish_with_scope` raises
   `PublicScopeNotAllowedForEnterpriseError` (HTTP 403) before any side
   effects.
3. **Database** — a CHECK constraint
   `registry_agent_profiles_public_only_default_tenant` refuses any row
   with `marketplace_scope='public_default_tenant'` whose `tenant_id`
   is not the well-known default-tenant UUID.

## Review lifecycle

Public submissions go through platform-staff review. A submission moves
through these states (`review_status`):

```
draft ──submit──▶ pending_review ──approve──▶ published ──deprecate──▶ deprecated
                       │
                       └──reject──▶ rejected ──resubmit──▶ pending_review
```

- **Submit** — owner POSTs `/api/v1/registry/agents/{id}/publish` with
  `scope: public_default_tenant` and a `marketing_metadata` block.
  Submission rate-limited to 5 per submitter per rolling 24h (FR-009).
- **Approve** — super admin or platform-staff POSTs
  `/api/v1/admin/marketplace-review/{id}/approve`.
- **Reject** — POSTs `/.../reject` with a required `reason`. The
  submitter is notified via the existing UPD-042 alert delivery.

Workspace and tenant scopes do **not** enter review — they transition
directly to `published`.

## Cross-tenant visibility (RLS)

The migration `108_marketplace_scope_and_review.py` replaces the original
`tenant_isolation` RLS policy on `registry_agent_profiles` with
`agents_visibility`. The policy keeps strict tenant isolation as the
default branch and adds two narrow exceptions for cross-tenant reads:

```sql
USING (
    -- default branch: tenant isolation
    tenant_id = current_setting('app.tenant_id', true)::uuid

    -- exception 1: default-tenant users see public-published agents
    OR (marketplace_scope = 'public_default_tenant'
        AND review_status = 'published'
        AND current_setting('app.tenant_kind', true) = 'default')

    -- exception 2: consume-flag-set tenants see public-published agents
    OR (marketplace_scope = 'public_default_tenant'
        AND review_status = 'published'
        AND current_setting('app.consume_public_marketplace', true) = 'true')
)
```

Both exception branches require `review_status = 'published'`, so
unapproved drafts never leak.

The `app.tenant_kind` and `app.consume_public_marketplace` GUCs are
bound automatically by the SQLAlchemy `before_cursor_execute` listener
in `apps/control-plane/src/platform/common/database.py` from the
`TenantContext`.

## Forking a public agent

Consumers can fork a visible public agent into their own tenant or
workspace. The fork is a shallow copy:

- Operational fields copied: prompts, capability declarations, tool
  dependencies, behaviour metadata.
- Reset on the fork: review status (back to `draft`), reviewer
  attribution, marketing metadata.
- Provenance: `forked_from_agent_id` points at the source.
- Source unchanged: forks do **not** auto-update on upstream changes;
  fork owners receive a `marketplace.source_updated` notification
  instead.

Endpoint: `POST /api/v1/registry/agents/{source_id}/fork`. See
[`contracts/fork-rest.md`](../../specs/099-marketplace-scope/contracts/fork-rest.md).

## Operator surface — `consume_public_marketplace`

Toggle the flag with a super-admin PATCH:

```bash
curl -X PATCH "$API/api/v1/admin/tenants/$TENANT_ID" \
  -H "Authorization: Bearer $SUPER_ADMIN_JWT" \
  -d '{ "feature_flags": { "consume_public_marketplace": true } }'
```

Only Enterprise tenants accept the flag. The default tenant refuses with
HTTP 422 (`feature_flag_invalid_for_tenant_kind`) — it's the publisher,
not a consumer.

Each toggle records a hash-linked audit-chain entry, publishes a
`tenants.feature_flag_changed` event on `tenants.lifecycle`, and
invalidates the resolver cache for the affected tenant. See
[`deploy/runbooks/marketplace-consume-flag.md`](../../deploy/runbooks/marketplace-consume-flag.md)
for the full operator runbook.

## Telemetry

Prometheus metrics (UPD-049 T079) exposed by the control plane:

| Metric | Type | Labels |
|---|---|---|
| `marketplace_submissions_total` | Counter | `category` |
| `marketplace_review_decisions_total` | Counter | `decision` |
| `marketplace_forks_total` | Counter | `target_scope` |
| `marketplace_rate_limit_refusals_total` | Counter | – |
| `marketplace_review_age_seconds` | Histogram | `decision` |

Grafana dashboard JSON:
[`deploy/helm/observability/dashboards/marketplace.json`](../../deploy/helm/observability/dashboards/marketplace.json).

## Kafka events

Topic: `marketplace.events`. Eight new event types:

- `marketplace.scope_changed`
- `marketplace.submitted`
- `marketplace.approved`
- `marketplace.rejected`
- `marketplace.published`
- `marketplace.deprecated`
- `marketplace.forked`
- `marketplace.source_updated`

Plus one new event on `tenants.lifecycle`:

- `tenants.feature_flag_changed`

See
[`contracts/marketplace-events-kafka.md`](../../specs/099-marketplace-scope/contracts/marketplace-events-kafka.md)
for envelope schemas.
