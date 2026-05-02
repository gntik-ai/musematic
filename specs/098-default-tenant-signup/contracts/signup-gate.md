# Contract — Signup Gate (Tenant-Kind Refusal)

**Affected endpoints**: `POST /api/v1/accounts/register`, `POST /api/v1/accounts/verify-email`, `POST /api/v1/accounts/resend-verification`.
**Owner**: `apps/control-plane/src/platform/accounts/router.py`
**Constitutional rule**: SaaS-3 (tenants are not self-serve), SaaS-19 (opaque 404 on non-default tenants).

## Behaviour

For every request to a signup-adjacent endpoint:

1. Read `request.state.tenant.kind` (set by UPD-046's hostname middleware).
2. If `kind == 'default'`: proceed with the existing UPD-037 logic (verification, anti-enumeration, OAuth handoff).
3. If `kind != 'default'` (currently only `enterprise`): return UPD-046's canonical opaque 404 — the response is byte-identical to the unknown-host 404 (`{"detail": "Not Found"}` body, no `X-Request-ID` echo, fixed `Content-Length`).

## Frontend mirror

`apps/web/app/(auth)/signup/page.tsx`: read `useTenantContext().kind` during SSR; if not `'default'`, call Next.js `notFound()` so the rendered page matches the backend's response shape.

## Verified behaviour

| Tenant kind | Response |
|---|---|
| `default` | UPD-037 unchanged: 202 anti-enumeration neutral on register; 200 on verify-email success. |
| `enterprise` | UPD-046 canonical opaque 404, byte-identical to unknown-host 404. |

## CI rule

`apps/control-plane/scripts/lint/check_signup_tenant_gate.py`: AST-walk the signup-adjacent router file; assert that every endpoint handler invokes the tenant-kind gate before any business logic. Failure fails the build.

## Test contract

Integration test `tests/integration/accounts/test_signup_at_enterprise_subdomain_404.py`:

- 50 candidate hostnames combining real Enterprise tenants and randomly-generated unknown subdomains; all 50 return byte-identical 404 (SC-002).
- Response timing variance below the documented enumeration-protection threshold from UPD-046.
- Probing pattern not specially logged (audit-chain has no entry; structlog has only the standard request line).
