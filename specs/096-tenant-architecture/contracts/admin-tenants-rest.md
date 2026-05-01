# Contract — Admin Tenants REST API

**Prefix**: `/api/v1/admin/tenants/*`
**Owner**: `apps/control-plane/src/platform/tenants/admin_router.py`
**Authorization**: Super admin role (`require_superadmin` dependency from UPD-036).
**OpenAPI tag**: `admin.tenants` (separate group per audit-pass rule 29).

All endpoints in this prefix run on the regular DB role and inherit RLS for the *resolved request tenant* (typically the default tenant when accessed via `app.musematic.ai/admin/...`). The router's repository methods that need cross-tenant reads explicitly use the platform-staff session (allowed within this admin namespace because the operation is super-admin-gated and the read is by ID, not a broad scan); cross-tenant *writes* go through `/api/v1/platform/tenants/*` instead.

## `GET /api/v1/admin/tenants`

List tenants with pagination and filters. Response body:

```jsonc
{
  "items": [
    {
      "id": "uuid",
      "slug": "acme",
      "kind": "enterprise",                  // "default" | "enterprise"
      "subdomain": "acme",
      "display_name": "Acme Corp",
      "region": "eu-central",
      "status": "active",                     // "active" | "suspended" | "pending_deletion"
      "scheduled_deletion_at": null,          // RFC 3339 when status == pending_deletion
      "created_at": "2026-05-01T10:00:00Z",
      "member_count": 42,                     // joined from accounts BC
      "active_workspace_count": 7,
      "subscription_summary": null            // populated when UPD-047 lands
    }
  ],
  "next_cursor": "opaque-token-or-null"
}
```

Query parameters: `kind`, `status`, `q` (slug or display-name substring), `cursor`, `limit` (max 100).

## `POST /api/v1/admin/tenants`

Provision a new Enterprise tenant. Request body:

```jsonc
{
  "slug": "acme",                              // required; regex-validated; rejected if reserved
  "display_name": "Acme Corp",                 // required; 1..128 chars
  "region": "eu-central",                      // required; member of allowed regions
  "first_admin_email": "cto@acme.com",         // required
  "dpa_artifact_id": "dpa-uuid-from-upload",   // required; references prior /admin/tenants/dpa-upload
  "dpa_version": "v3-2026-01",                 // required
  "contract_metadata": {                       // optional free-form
    "contract_number": "ACME-2026-001",
    "signed_at": "2026-04-30",
    "signed_by": "Alice CTO"
  },
  "branding_config": {                         // optional
    "logo_url": "https://...",
    "accent_color_hex": "#0078d4"
  }
}
```

Response 201:

```jsonc
{
  "id": "uuid",
  "slug": "acme",
  "subdomain": "acme",
  "kind": "enterprise",
  "status": "active",
  "first_admin_invite_sent_to": "cto@acme.com",
  "dns_records_pending": true                  // resolves to false within ~5 minutes
}
```

Response 422 — `slug_reserved` | `slug_invalid` | `slug_taken` | `dpa_missing` | `region_invalid`.

Side effects: writes `tenants` row, emits `tenants.created` Kafka event, records audit chain entry, calls Hetzner DNS automation, sends first-admin invitation through notifications BC.

## `GET /api/v1/admin/tenants/{id}`

Fetch a single tenant including the full branding config, DPA metadata, contract metadata, and recent lifecycle audit entries. Returns 404 if not found.

## `PATCH /api/v1/admin/tenants/{id}`

Update a tenant. Body fields optional; allowed: `display_name`, `region`, `branding_config`, `contract_metadata`, `feature_flags`. Refuses any change to `slug`, `subdomain`, `kind`, or `status` (status changes go through their dedicated endpoints below). For `kind='default'` the trigger refuses display_name/region change as well — only branding overrides are permitted.

## `POST /api/v1/admin/tenants/{id}/suspend`

Body:

```jsonc
{ "reason": "Non-payment, contract days past due" }
```

Transitions status to `suspended`. Refused for the default tenant. Audit-chain + Kafka emitted.

## `POST /api/v1/admin/tenants/{id}/reactivate`

Empty body. Transitions `suspended → active` or `pending_deletion → active` (cancels deletion). Refused for the default tenant. Audit-chain + Kafka emitted.

## `POST /api/v1/admin/tenants/{id}/schedule-deletion`

Body:

```jsonc
{
  "reason": "End of contract; customer-requested cleanup",
  "two_pa_token": "..."                        // required: 2PA per audit-pass rule 33
}
```

Transitions to `pending_deletion`, sets `scheduled_deletion_at = now() + grace_period`. Refused for the default tenant. Returns `scheduled_deletion_at`. Audit-chain + Kafka emitted.

## `POST /api/v1/admin/tenants/{id}/cancel-deletion`

Empty body. Reverts `pending_deletion → active`. Audit-chain + Kafka emitted.

## `POST /api/v1/admin/tenants/dpa-upload`

Multipart file upload (PDF). Stores in S3 bucket `tenant-dpas` at a temporary path. Response includes `dpa_artifact_id` to be used in the subsequent `POST /api/v1/admin/tenants` call.

## Error model

All error responses follow the canonical `PlatformError` shape (`code`, `message`, `details`).

| HTTP | `code` examples |
|---|---|
| 400 | `bad_request` |
| 401 | `unauthenticated` |
| 403 | `forbidden`, `not_super_admin` |
| 404 | `tenant_not_found` |
| 409 | `slug_taken`, `default_tenant_immutable`, `concurrent_lifecycle_action` |
| 422 | `slug_reserved`, `slug_invalid`, `dpa_missing`, `region_invalid`, `2pa_required` |
| 500 | `dns_automation_failed` (subdomain DNS not reachable within SLA) |
