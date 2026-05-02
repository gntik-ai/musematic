# Contract — Per-Tenant `consume_public_marketplace` Feature Flag

**Affected endpoint**: extends `apps/control-plane/src/platform/tenants/admin_router.py:PATCH /api/v1/admin/tenants/{id}`.
**OpenAPI tag**: `admin.tenants`.
**Authorization**: super admin only.

## `PATCH /api/v1/admin/tenants/{id}` (extended)

Existing PATCH endpoint gains an optional `feature_flags` field that routes through
`TenantsService.set_feature_flag` for per-flag validation + audit + Kafka.

```jsonc
{
  "feature_flags": {
    "consume_public_marketplace": true
  }
}
```

Behaviour:

- Flags in the documented allowlist (currently just `consume_public_marketplace`)
  route through `TenantsService.set_feature_flag` for full validation, audit, and
  Kafka. Flags **not** in the allowlist preserve the legacy "set the whole dict"
  semantics for backward compatibility — pre-existing custom flags continue to
  work without code changes (this is the brownfield-compat note: see
  `specs/099-marketplace-scope/NOTES.md`).
- The `consume_public_marketplace` flag is allowed only on Enterprise tenants
  (the default tenant is a publisher, not a consumer). Setting it on the default
  tenant → `422 feature_flag_invalid_for_tenant_kind`.
- A successful set:
  - Updates `tenants.feature_flags` JSONB.
  - Records a hash-linked audit-chain entry (payload includes from/to values).
  - Publishes `tenants.feature_flag_changed` on `tenants.lifecycle` (see
    `marketplace-events-kafka.md`).
  - Invalidates the tenant resolver cache for that tenant (next request re-reads).

## Response

Updated `TenantView` mirroring the existing PATCH response shape with the new
`feature_flags` block included.

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 403 | `not_super_admin` |
| 404 | `tenant_not_found` |
| 422 | `feature_flag_invalid_for_tenant_kind` (and `feature_flag_not_in_allowlist` is reserved for future strict-mode operation) |

## Test contract

Unit + integration tests in `tests/unit/tenants/test_set_feature_flag.py` and
`tests/integration/tenants/test_admin_patch_feature_flags.py`:

- Setting `consume_public_marketplace=true` on Enterprise tenant succeeds; audit-chain
  entry recorded; Kafka event published; resolver cache invalidated.
- Setting on default tenant returns 422.
- Setting unknown flag returns 422.
- Toggling the flag back to false succeeds and is reflected in the resolver on next
  request.
