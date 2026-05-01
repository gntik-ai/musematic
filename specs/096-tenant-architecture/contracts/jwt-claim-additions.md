# Contract — JWT Claim Additions (`tenant_id`, `tenant_slug`, `tenant_kind`)

**Owner**: `apps/control-plane/src/platform/auth/jwt_service.py`
**Companion contract**: `tenant-resolution-context.md` (the runtime tenant context).

## Additive claims

The platform's RS256 access token (issued by the auth BC) gains three additive claims:

```jsonc
{
  // existing claims (sub, exp, iat, iss, aud, scopes, …)
  "tenant_id": "uuid",
  "tenant_slug": "acme",
  "tenant_kind": "enterprise"
}
```

Refresh tokens carry `tenant_id` only (kind/slug are stable per tenant_id and re-fetched on access-token refresh).

## Backward compatibility

- The new claims are **additive**. Tokens issued by previous versions (no claims) continue to validate; the auth middleware treats a missing `tenant_id` claim as "default tenant" during the lenient-rollout window. Strict mode rejects tokens without `tenant_id`.
- Token issuance always includes the claims after the migration; existing sessions naturally roll over to enriched tokens within the access-token TTL (15 minutes per UPD-014).

## Validation contract

Auth middleware (`auth/auth_middleware.py`) validates that:

1. The token is signed correctly (existing rule).
2. The token's `tenant_id` claim matches the resolved tenant from the hostname middleware. Mismatch → 401 with `code=tenant_mismatch`. This blocks an attacker who steals a token from `app.musematic.ai` and tries to use it against `acme.musematic.ai`.
3. The token's `tenant_kind` claim matches the resolved tenant's kind. Mismatch → 401 (catches a default-tenant token replayed against an Enterprise subdomain after that tenant was just provisioned).

## Cross-tenant identity

A user with the same email in two tenants has two separate user records, two separate credential rows, and two separate token chains. There is no single sign-on across tenants in this feature (out of scope per the spec assumption).

## Test contract

Unit tests in `tests/unit/tenants/test_jwt_claims.py`:

- A token issued for the default tenant carries `tenant_id = default UUID`, `tenant_slug = "default"`, `tenant_kind = "default"`.
- A token issued for tenant Acme carries Acme's claims.
- A token from Acme presented to `app.musematic.ai` is rejected with `code=tenant_mismatch`.
- A pre-migration token (no claims) is accepted in lenient mode and rejected in strict mode.
