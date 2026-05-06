# Contract — `tests/e2e/fixtures/tenants.py`

## Purpose

Provision, expose, and clean up Enterprise tenants for journey tests via the public super-admin API. Every E2E journey that needs an Enterprise tenant goes through this fixture; no journey performs raw `INSERT INTO tenants ...` against PostgreSQL.

## Public Surface

```python
from contextlib import asynccontextmanager
from uuid import UUID

@asynccontextmanager
async def provision_enterprise(
    *,
    slug: str | None = None,                # auto-generated when None
    plan: str = "enterprise",                # "free" | "pro" | "enterprise"
    region: str = "eu-central",
    super_admin_client: AuthenticatedAsyncClient,
    dpa_artifact: bytes | None = None,       # optional DPA upload bytes
    first_admin_email: str | None = None,    # auto-generated when None
) -> AsyncIterator[TestTenant]:
    """Provision an Enterprise tenant via POST /api/v1/admin/tenants and
    yield a TestTenant handle. On exit, schedule + complete deletion via
    the admin API. Idempotent teardown (404 treated as success).

    The fixture polls the audit chain for `tenants.created` to confirm
    the side-effect chain completed before yielding, so journey bodies
    can assume the tenant is ready to receive traffic.
    """


async def list_test_tenants(
    *,
    super_admin_client: AuthenticatedAsyncClient,
    slug_prefix: str = "e2e-",
) -> list[TestTenant]:
    """SC-006 helper. Lists every tenant whose slug starts with the test
    prefix; used by the soak-run cleanup verifier and by manual cleanup
    scripts. Returns an empty list when no orphans remain.
    """
```

## Behaviour

### `provision_enterprise`

1. Generate a slug (`e2e-{worker-id}-{8-char-uuid}`) when not supplied. Always `e2e-` prefix to make orphan detection cheap.
2. POST `/api/v1/admin/tenants` with the slug, plan, region, DPA artefact, and a deterministic `first_admin_email` of the form `e2e-{slug}-admin@e2e.musematic-test.invalid`.
3. Poll `audit_chain_entries` (via the read-only `db_session` fixture) for an entry with `event_type=tenants.created` and `tenant_id=<returned id>` for up to 30 seconds.
4. Poll the DNS provider's `verify_propagation(...)` for `<slug>.musematic-test.invalid` (mock) OR the live Hetzner test zone (`RUN_J29=1`) for up to 5 minutes.
5. Yield a `TestTenant` with all fields populated.
6. On exit (whether via success or exception), call `POST /api/v1/admin/tenants/{slug}/schedule-deletion` then `POST /api/v1/admin/tenants/{slug}/complete-deletion`. 404 from either endpoint is treated as success (the test may have already cleaned up). Failures other than 404 are raised AFTER the journey's primary assertions have completed (so the journey error is preserved as the root cause).

### Cleanup safety guards

- The fixture enforces `slug.startswith("e2e-")` before calling `complete-deletion`. This guards against an accidentally hand-typed slug colliding with a real tenant.
- The fixture refuses to operate on the canonical default tenant (slug = `default`); any attempt raises `ValueError` immediately.
- Concurrent fixture invocations from `pytest-xdist` workers are isolated by the `e2e-{worker-id}-` prefix.

## Failure modes & exceptions

| Exception | When | Handler expectation |
|---|---|---|
| `TenantProvisioningTimeoutError` | DNS propagation didn't complete within 5 minutes | Journey reports a setup failure with the failure-artefact bundle including the DNS resolver state |
| `AuditChainTimeoutError` | `tenants.created` didn't appear in the audit chain within 30 seconds | Journey reports a setup failure; bundles the latest 10 audit entries |
| `TenantCleanupError` | Teardown failed with anything other than 404 | Logged at error level; the journey's primary failure (if any) takes precedence |

## Cross-references

- The admin API surface is the one delivered by UPD-053 / UPD-049 (super-admin + marketplace-scope endpoints).
- Audit chain reads use the `db_session` fixture; no direct asyncpg.
- The fixture is reused by **every** new journey that operates on a tenant other than `default` (J22, J24, J25, J27, J29, J31, J36).
