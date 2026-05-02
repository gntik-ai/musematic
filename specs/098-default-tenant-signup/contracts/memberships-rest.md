# Contract — Memberships REST API

**Prefix**: `/api/v1/me/memberships`
**Owner**: `apps/control-plane/src/platform/accounts/memberships_router.py` (mounted under existing `/api/v1/me/*` namespace)
**Authorization**: Authenticated user only.
**OpenAPI tag**: `me.memberships`.
**Database session**: This endpoint uses the platform-staff session (`BYPASSRLS`) per research R2 because users are tenant-scoped; the cross-tenant lookup is the only path in this feature that requires `BYPASSRLS`.

## `GET /api/v1/me/memberships`

Returns the authenticated user's full list of tenant memberships.

**Response 200**:

```jsonc
{
  "memberships": [
    {
      "tenant_id": "00000000-0000-0000-0000-000000000001",
      "tenant_slug": "default",
      "tenant_kind": "default",
      "tenant_display_name": "Musematic",
      "user_id_within_tenant": "uuid",
      "role": "workspace_owner",
      "is_current_tenant": true,
      "login_url": "https://app.musematic.ai/login"
    },
    {
      "tenant_id": "uuid",
      "tenant_slug": "acme",
      "tenant_kind": "enterprise",
      "tenant_display_name": "Acme Corp",
      "user_id_within_tenant": "uuid",
      "role": "tenant_admin",
      "is_current_tenant": false,
      "login_url": "https://acme.musematic.ai/login"
    }
  ],
  "count": 2
}
```

The `is_current_tenant` flag identifies the tenant the request currently resolves to (matches `request.state.tenant.id`). The `login_url` constructs the deep-link the tenant switcher uses on click.

## Privacy contract

The endpoint MUST surface only memberships the authenticated user holds. Achieved by SQL-level filtering: `WHERE users.email = :authenticated_user_email AND users.status = 'active'`. The endpoint never reveals the existence of tenants the user does not belong to.

## Test contract

Integration test `tests/integration/accounts/test_me_memberships_endpoint.py`:

- A user with 0 memberships (impossible in practice — every authenticated user holds at least the resolved tenant) — `count=0`, `memberships=[]`.
- A user with exactly 1 membership — `count=1`, the resolved tenant is returned with `is_current_tenant=true`.
- A user with 3 memberships — all three returned, the resolved one marked.
- Two users with the same email but in different tenants — each user's `/me/memberships` call returns the other user's tenants too (because email-as-correlator is the join key per FR-022) — both users see both tenants.
- A user requesting from tenant A — the response includes tenant A; tenant B membership is included; tenants C / D / E that the user does NOT belong to are NOT included (zero false positives, zero false negatives — SC-010).

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 500 | (rare) `platform_staff_session_unavailable` — only when the platform-staff DB engine is misconfigured |
