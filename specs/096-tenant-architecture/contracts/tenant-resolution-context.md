# Contract — Tenant Resolution Context (Backend)

**Owner**: `apps/control-plane/src/platform/common/middleware/tenant_resolver.py`
**Companion**: `apps/control-plane/src/platform/common/tenant_context.py` (ContextVar + dataclass)

## The `TenantContext` dataclass

```python
@dataclass(frozen=True)
class TenantContext:
    id: UUID                        # tenants.id
    slug: str                       # tenants.slug
    subdomain: str                  # tenants.subdomain
    kind: Literal["default", "enterprise"]
    status: Literal["active", "suspended", "pending_deletion"]
    region: str
    branding: TenantBranding        # frozen view of branding_config_json
    feature_flags: Mapping[str, Any]
```

Lives in a `ContextVar[TenantContext | None]` named `current_tenant` declared in `tenant_context.py`. Set by `TenantResolverMiddleware` at request entry; read everywhere else via `get_current_tenant()` helper that raises `TenantContextNotSetError` if called outside a request scope.

## Middleware contract

```python
class TenantResolverMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        host = self._normalize_host(request.headers.get("host"))
        tenant = await self._resolve(host)              # tier-1 LRU → tier-2 Redis → DB
        if tenant is None:
            return self._build_opaque_404()              # see R6 — byte-identical
        if tenant.status == "pending_deletion" and not _is_platform_staff(request):
            return self._build_opaque_404()              # subdomain unreachable during deletion grace
        token = current_tenant.set(tenant)
        request.state.tenant = tenant                    # also exposed via request.state for non-Python contexts
        try:
            return await call_next(request)
        finally:
            current_tenant.reset(token)
```

The middleware is registered LAST in `create_app()` so that Starlette's reverse-registration order makes it the outermost (first-executing) layer.

## Hostname normalization

- Strip port (`:443`, `:80`, `:8080`).
- Lower-case.
- Reject anything not ending with `PLATFORM_DOMAIN` (e.g., `musematic.ai` in production, `dev.musematic.ai` in dev) → 404.

## Subdomain → tenant lookup rules

Given `host = <prefix>.<platform_domain>`:

| Prefix pattern | Resolved tenant |
|---|---|
| (empty) — bare `musematic.ai` | (per `R*` decision: deterministic landing tenant — for now, default tenant; under operator policy can be changed to a marketing-page-only response) |
| `app` | default tenant |
| `api` | default tenant |
| `grafana` | default tenant |
| `<slug>` (where `<slug>` is the subdomain of an enterprise tenant) | that tenant |
| `<slug>.api` | that tenant (API surface) |
| `<slug>.grafana` | that tenant (Grafana surface) |
| anything else | 404 (opaque) |

Reserved single-label prefixes `status`, `webhooks`, `www`, `admin`, `platform`, `public`, `docs`, `help` either have their own routing logic outside the tenant resolver (e.g., `webhooks.musematic.ai` is the Stripe webhook endpoint per SaaS-18 and resolves to a tenant-agnostic handler) or are left as 404 here and handled by ingress.

## Database-session binding

A SQLAlchemy `before_cursor_execute` event on `regular_engine`:

```python
@event.listens_for(regular_engine.sync_engine, "before_cursor_execute")
def _bind_tenant_id(conn, cursor, statement, params, context, executemany):
    tenant = current_tenant.get(None)
    if tenant is None:
        return  # platform-staff session or out-of-request context — caller is responsible
    cursor.execute(
        f"SET LOCAL app.tenant_id = '{tenant.id}'"
    )
```

The `SET LOCAL` ties the GUC to the active transaction. The regular role lacks `BYPASSRLS`, so any query without an explicit `tenant_id` filter falls back to the RLS policy — defense in depth as required by SaaS-11.

## Test contract

Unit tests in `tests/unit/tenants/test_resolver.py`:

- Default tenant resolves from `app.musematic.ai`.
- Enterprise tenant resolves from its `<slug>.musematic.ai`.
- Unknown subdomain returns 404.
- Hostname is case-insensitive.
- Port strip works for `:80`, `:443`, `:8080`.
- Suspended tenant subdomain still resolves (the suspension banner renders inside the page).
- `pending_deletion` tenant subdomain returns opaque 404 to non-platform-staff.
- 100 randomly-selected unresolved hosts produce byte-identical responses (SC-009).

Integration tests in `tests/integration/tenants/test_hostname_middleware.py`:

- Cache-miss path queries the DB once and writes Redis.
- Cache-hit path skips the DB entirely (asserted via mock query counter).
- Tenant attribute change emits Redis pub/sub invalidation; the next request rebuilds the cache.
- p95 cache-resident latency under the 5 ms threshold (SC-005).
