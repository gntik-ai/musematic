# Contract — Platform-Staff Tenants REST API

**Prefix**: `/api/v1/platform/tenants/*`
**Owner**: `apps/control-plane/src/platform/tenants/platform_router.py`
**Authorization**: Platform-staff role (a separate role above super admin; only Anthropic-operated platform engineers).
**Database role**: `musematic_platform_staff` (`BYPASSRLS`) via `get_platform_staff_session()` dependency.
**OpenAPI tag**: `platform.tenants`.

This is the only namespace where cross-tenant reads and writes are permitted. The CI rule for `BYPASSRLS` segregation (FR-042) enforces that no other route prefix references `get_platform_staff_session`.

## `GET /api/v1/platform/tenants`

Cross-tenant listing for platform engineering. Same response shape as `/api/v1/admin/tenants`, but unrestricted by the request's resolved tenant. Supports the same filters plus `include_deleted=true` (returns rows whose row was tombstoned in audit chain — derived from audit projections, not from the live `tenants` table since deletion is a hard delete after grace).

## `GET /api/v1/platform/tenants/{id}`

Cross-tenant single-tenant fetch. Always succeeds for platform staff regardless of the request's resolved tenant.

## `GET /api/v1/platform/tenants/{id}/health`

Returns operational health summary for a tenant: row counts per major table (workspaces, users, executions), DNS reachability, recent error rate, secrets scope path scan result. Used by the on-call dashboard and during incident triage.

## `POST /api/v1/platform/tenants/{id}/force-cascade-deletion`

Bypasses the grace period and immediately runs the deletion cascade. Requires 2PA + platform-staff incident-mode flag. Emits a critical audit-chain entry. Refused for the default tenant.

## `GET /api/v1/platform/workspaces/{id}` (and similar cross-tenant resource fetchers)

User Story 3 explicitly contemplates platform-staff cross-tenant resource access — these read-only fetchers exist for incident triage. Each emits an audit-chain entry tagged with the actor (platform staff) and the subject tenant.

## Error model

Same as `/api/v1/admin/tenants/*`. Additional `code` values:

| HTTP | `code` |
|---|---|
| 403 | `not_platform_staff` (super admin attempting platform-staff endpoint) |
| 409 | `force_cascade_refused_for_default_tenant` |

## Audit and observability

Every successful platform-staff action emits an audit-chain entry of `event_type=platform.tenants.<action>` with `actor_role=platform_staff`. The Grafana dashboard `tenants.yaml` tracks the rate of platform-staff cross-tenant access; sustained elevated rates trigger an alert (configured by UPD-080 incident response).
