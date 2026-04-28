# Software Architecture — v6 (Post SaaS Pass)

> Supersedes `software-architecture-v5.md` for tenant-aware bounded contexts, billing layer, and platform-staff endpoint segregation.

---

## 1. Bounded Context Map

```
control-plane/
  ├── platform/
  │   ├── tenants/                    # NEW (UPD-046)
  │   ├── billing/                    # NEW
  │   │   ├── plans/                  # UPD-047
  │   │   ├── subscriptions/          # UPD-047
  │   │   ├── quotas/                 # UPD-047
  │   │   └── providers/              # UPD-052 PaymentProvider abstraction
  │   ├── data_lifecycle/             # NEW (UPD-051)
  │   ├── marketplace/                # MODIFIED (UPD-049 multi-scope)
  │   ├── security/
  │   │   └── abuse_prevention/       # NEW (UPD-050)
  │   ├── audit_chain/                # MODIFIED (tenant_id in entries)
  │   ├── cost_governance/            # MODIFIED (tenant_id in cost records, plan/sub linkage)
  │   ├── secrets/                    # MODIFIED (tenant-scoped Vault paths)
  │   └── identity/
  │       ├── accounts/               # MODIFIED (UPD-048 default tenant constraint)
  │       ├── memberships/            # MODIFIED (cross-tenant memberships)
  │       └── oauth/                  # MODIFIED (per-tenant configs)
  ├── middleware/
  │   ├── tenant_resolver.py          # NEW (UPD-046, first in pipeline)
  │   ├── auth.py
  │   ├── rate_limit.py               # MODIFIED (per-tenant rate limits)
  │   └── audit.py                    # MODIFIED (tenant_id in entries)
  └── api/
      ├── public/                     # /api/v1/...
      ├── admin/                      # /admin/... super-admin scoped
      └── platform/                   # /api/v1/platform/... uses platform-staff role

data-plane/
  └── execution/                      # MODIFIED (tenant_id propagation through events)

frontend/
  ├── shell/
  │   └── tenant-switcher/            # NEW (when user has multi-tenant memberships)
  ├── pages/
  │   ├── billing/                    # NEW
  │   ├── onboarding/                 # NEW
  │   ├── setup/                      # NEW (Enterprise tenant first admin)
  │   └── (admin pages — modified for tenant-aware filtering)
```

---

## 2. Tenant Bounded Context

```
tenants/
├── models.py
│   ├── Tenant
│   ├── TenantKind (enum: default, enterprise)
│   ├── TenantStatus (enum: active, suspended, pending_deletion)
│   └── TenantBranding
├── repository.py                     # platform-staff role for cross-tenant queries
├── service.py
│   ├── provision_default_tenant()    # at install
│   ├── provision_enterprise_tenant() # super admin
│   ├── suspend_tenant()
│   ├── recover_suspended_tenant()
│   ├── initiate_deletion_phase_1()
│   ├── execute_deletion_phase_2()    # cascade
│   ├── recover_pending_deletion()
│   └── update_tenant_config()
├── router.py                         # tenant context endpoints
├── admin_router.py                   # /admin/tenants
├── platform_router.py                # /api/v1/platform/tenants (cross-tenant)
├── seeder.py                         # default tenant seed
├── dns_automation.py                 # Hetzner DNS API client
├── vault_paths.py                    # tenant-scoped Vault path helpers
└── events.py                         # Kafka events: tenant.provisioned, .suspended, .deleted
```

### Lifecycle Events

```python
class TenantLifecycleEvent(BaseEvent):
    tenant_id: UUID
    event_type: Literal['provisioned', 'suspended', 'reactivated', 'deletion_phase_1', 'deletion_phase_2_completed', 'recovered']
    previous_status: TenantStatus | None
    new_status: TenantStatus | None
    actor_user_id: UUID | None
    metadata: dict
```

Consumers:
- `dns_automation` listens to `provisioned` to create DNS records.
- `dns_automation` listens to `deletion_phase_2_completed` to remove DNS records.
- `audit_chain` listens to all events.
- `notification_center` listens to `provisioned` (notify first admin), `suspended` (notify tenant), etc.

---

## 3. Billing Bounded Context

### Plans Sub-context

```python
class PlanService:
    async def publish_new_version(self, plan_id: UUID, params: PlanVersionParams, actor: UUID) -> PlanVersion:
        # Atomic version increment + insert
        async with self.db.transaction():
            current = await self.repo.get_current_published(plan_id)
            new_version_num = (current.version + 1) if current else 1
            new_v = await self.repo.insert_version(plan_id, new_version_num, params)
            await self.repo.publish(new_v.id)
            await self.audit.log(actor, 'plan.version.published', new_v.id, params=params)
            return new_v
```

### Subscriptions Sub-context

```python
class SubscriptionService:
    async def create_for_workspace(self, workspace_id: UUID, plan_id: UUID, payment_method_id: UUID | None) -> Subscription:
        # 1. Get current published plan version
        # 2. If price > 0 and payment_method required: validate
        # 3. Call PaymentProvider.create_subscription() (Stripe)
        # 4. Wait for webhook customer.subscription.created OR poll briefly
        # 5. Insert local subscription with stripe_subscription_id
        # 6. Audit
        # 7. Return

    async def upgrade_to(self, subscription_id: UUID, new_plan_id: UUID, actor: UUID) -> Subscription:
        # 1. Get current sub + new plan version
        # 2. PaymentProvider.update_subscription() with proration
        # 3. Update local sub
        # 4. Audit, notify
        # 5. Quotas immediately apply

    async def cancel(self, subscription_id: UUID, at_period_end: bool, reason: str, actor: UUID):
        # 1. PaymentProvider.cancel_subscription()
        # 2. Update local status to cancellation_pending (or canceled if immediate)
        # 3. Audit, notify
```

### Quotas Sub-context

```python
class QuotaEnforcer:
    """Synchronous quota check before any quota-bound operation."""

    async def check_execution(self, workspace_id: UUID, projected_minutes: float) -> QuotaCheckResult:
        # Cached lookups (Redis with 60s TTL)
        sub = await self._get_active_sub_cached(workspace_id)
        plan_v = await self._get_plan_version_cached(sub.plan_id, sub.plan_version)
        usage = await self._get_current_usage_cached(sub.id, sub.current_period_start)
        # Return: OK, HARD_CAP_EXCEEDED, OVERAGE_REQUIRED, OVERAGE_AUTHORIZED
        ...

class MeteringJob:
    """Kafka consumer aggregating execution.compute.* events into usage_records."""

class OverageService:
    async def authorize_for_period(self, workspace_id: UUID, period_start: datetime, max_overage_eur: Decimal | None, authorized_by: UUID):
        # Idempotent insert (UNIQUE on workspace_id + billing_period_start)
        # Resume any paused executions for this workspace
        ...
```

### Providers Sub-context

```python
# providers/interface.py
class PaymentProvider(Protocol):
    async def create_customer(self, tenant_id: UUID, email: str, metadata: dict) -> str: ...
    async def attach_payment_method(self, customer_id: str, token: str) -> PaymentMethodInfo: ...
    async def create_subscription(self, customer_id: str, plan_price_id: str, trial_days: int, overage_price_id: str | None) -> SubscriptionInfo: ...
    async def update_subscription(self, sub_id: str, **kwargs) -> SubscriptionInfo: ...
    async def cancel_subscription(self, sub_id: str, at_period_end: bool = True) -> None: ...
    async def report_usage(self, sub_item_id: str, quantity: int, ts: datetime) -> None: ...
    async def charge_overage(self, customer_id: str, amount_cents: int, description: str) -> str: ...
    async def create_customer_portal_session(self, customer_id: str, return_url: str) -> str: ...
    async def verify_webhook_signature(self, payload: bytes, signature: str) -> WebhookEvent: ...
    async def handle_webhook_event(self, event: WebhookEvent) -> None: ...

# providers/stripe/provider.py
class StripePaymentProvider(PaymentProvider):
    """Concrete Stripe impl using stripe-python SDK."""
    ...

# providers/stub/provider.py  
class StubPaymentProvider(PaymentProvider):
    """For tests and offline mode."""
    ...

# providers/factory.py
def get_payment_provider() -> PaymentProvider:
    provider_name = settings.BILLING_PROVIDER
    if provider_name == 'stripe':
        return StripePaymentProvider(...)
    elif provider_name == 'stub':
        return StubPaymentProvider()
    else:
        raise ValueError(f'Unknown provider: {provider_name}')
```

---

## 4. Data Lifecycle Bounded Context

```
data_lifecycle/
├── export_service.py
│   ├── request_workspace_export()
│   ├── request_tenant_export()
│   └── execute_export_job()        # background worker
├── deletion_service.py
│   ├── request_workspace_deletion()
│   ├── request_tenant_deletion()
│   ├── execute_phase_1()
│   ├── execute_phase_2_cascade()    # delete data, DNS, Vault, OAuth
│   └── recover_during_grace()
├── dpa_service.py
│   ├── upload_for_tenant()          # virus scan + Vault store
│   └── retrieve_for_tenant()
├── sub_processors_service.py
│   └── publish_to_static_page()
├── backup_purge.py
│   └── purge_deleted_tenant_data() # scheduled
└── workers/
    ├── export_worker.py
    └── grace_monitor.py
```

---

## 5. Marketplace Multi-Scope Refactor

```
marketplace/
├── models.py
│   ├── MarketplaceScope (enum: workspace, tenant, public_default_tenant)
│   └── ReviewStatus (enum: draft, pending_review, approved, rejected, published, deprecated)
├── service.py                       # extended with scope handling
├── review_service.py                # review queue ops
├── visibility.py                    # query helper for scope-aware retrieval
├── router.py                        # /api/v1/marketplace
└── admin_router.py                  # /admin/marketplace-review
```

Visibility helper:

```python
class MarketplaceVisibilityHelper:
    @staticmethod
    def applicable_scopes_for_tenant(tenant: Tenant) -> list[MarketplaceScope]:
        scopes = [MarketplaceScope.WORKSPACE, MarketplaceScope.TENANT]
        if tenant.kind == 'default':
            scopes.append(MarketplaceScope.PUBLIC_DEFAULT_TENANT)
        elif tenant.feature_flags.get('consume_public_marketplace', False):
            scopes.append(MarketplaceScope.PUBLIC_DEFAULT_TENANT)
        return scopes
```

---

## 6. Hostname-to-Tenant Middleware

```python
class TenantResolverMiddleware:
    def __init__(self, app, tenant_repo, redis_client, settings):
        self.app = app
        self.tenant_repo = tenant_repo
        self.redis = redis_client
        self.platform_domain = settings.PLATFORM_DOMAIN  # 'musematic.ai' or 'dev.musematic.ai'
        self.cache_ttl = 60  # seconds

    async def __call__(self, request, call_next):
        host = self._normalize_host(request.headers.get('host', ''))
        if not host.endswith(self.platform_domain):
            return JSONResponse({'error': 'unknown_host'}, status_code=404)

        slug = self._extract_slug(host)
        tenant = await self._resolve_tenant(slug)
        if not tenant or tenant.status not in ['active']:
            return JSONResponse({'error': 'not_found'}, status_code=404)

        request.state.tenant = tenant
        request.state.tenant_kind = tenant.kind

        # Set RLS session variable
        async with request.state.db.begin():
            await request.state.db.execute(
                text("SELECT set_config('app.tenant_id', :tid, true), set_config('app.tenant_kind', :tkind, true), set_config('app.consume_public_marketplace', :cpm, true)"),
                {
                    'tid': str(tenant.id),
                    'tkind': tenant.kind,
                    'cpm': str(tenant.feature_flags.get('consume_public_marketplace', False)).lower(),
                }
            )
            return await call_next(request)

    def _normalize_host(self, host: str) -> str:
        return host.split(':')[0].lower()

    def _extract_slug(self, host: str) -> str:
        # 'app.musematic.ai' -> 'app' -> default tenant
        # 'acme.musematic.ai' -> 'acme'
        # 'acme.api.musematic.ai' -> 'acme' (api is sub-path)
        prefix = host[:-(len(self.platform_domain) + 1)] if host != self.platform_domain else ''
        if not prefix:
            return ''  # apex
        parts = prefix.split('.')
        # Special: 'api', 'grafana', 'app' all default tenant
        if len(parts) == 1 and parts[0] in ('app', 'api', 'grafana'):
            return 'default'
        # 'acme.api' -> first part is tenant slug
        return parts[0]

    async def _resolve_tenant(self, slug: str) -> Tenant | None:
        cache_key = f'tenant:slug:{slug}'
        cached = await self.redis.get(cache_key)
        if cached:
            return Tenant.parse_raw(cached)
        if not slug:
            tenant = await self.tenant_repo.get_default()
        else:
            tenant = await self.tenant_repo.get_by_slug(slug)
        if tenant:
            await self.redis.setex(cache_key, self.cache_ttl, tenant.json())
        return tenant
```

---

## 7. Platform-Staff Endpoint Segregation

```python
# Two database connection pools

# Regular pool — uses musematic_app role (no BYPASSRLS)
app_pool = create_async_engine(
    'postgresql+asyncpg://musematic_app:...@postgres-primary/musematic',
    pool_size=50,
)

# Platform-staff pool — uses musematic_platform_staff role (BYPASSRLS)
platform_pool = create_async_engine(
    'postgresql+asyncpg://musematic_platform_staff:...@postgres-primary/musematic',
    pool_size=10,  # smaller; only super admin uses
)

# Routes choose pool via dependency
async def get_app_db():
    async with app_pool.connect() as conn:
        yield conn

async def get_platform_db():
    async with platform_pool.connect() as conn:
        yield conn

# Regular endpoints
@router.get('/api/v1/agents/{fqn}')
async def get_agent(fqn: str, db: AsyncConnection = Depends(get_app_db)):
    # uses musematic_app, RLS enforced
    ...

# Platform-staff endpoints
@platform_router.get('/api/v1/platform/tenants')
async def list_all_tenants(db: AsyncConnection = Depends(get_platform_db), current_user = Depends(require_super_admin)):
    # uses musematic_platform_staff, BYPASSRLS, sees all tenants
    ...
```

CI check: any code using `get_platform_db` outside `apps/control-plane/src/api/platform/` fails build.

---

## 8. Frontend Tenant Awareness

```typescript
// app/tenant-context.tsx
export const TenantContext = createContext<{
  tenant: Tenant;
  branding: BrandingConfig;
  features: TenantFeatureFlags;
}>(...);

// app/layout.tsx
export default async function RootLayout({children}) {
  const tenant = await fetchCurrentTenant();  // From server-side host header
  return (
    <TenantProvider value={tenant}>
      <ApplyBrandingCss tenant={tenant}>
        {children}
      </ApplyBrandingCss>
    </TenantProvider>
  );
}

// components/tenant-switcher.tsx
function TenantSwitcher() {
  const memberships = useMemberships();
  if (memberships.length < 2) return null;
  return (
    <Select onChange={(slug) => window.location.href = `https://${slug}.musematic.ai/`}>
      {memberships.map(m => <option key={m.tenant_id}>{m.tenant_display_name}</option>)}
    </Select>
  );
}
```

---

## 9. Background Workers

| Worker | Purpose | Trigger |
|---|---|---|
| `MeteringJob` | Aggregate execution.compute.end events into usage_records | Kafka consumer |
| `QuotaPeriodResetScheduler` | Advance subscriptions whose current_period_end has passed | Cron (every minute) |
| `PaymentFailureGraceMonitor` | Track grace progression, send daily reminders, downgrade on day 7 | Cron (every hour) |
| `ExportJobWorker` | Generate workspace/tenant export ZIPs | Kafka consumer |
| `GraceMonitor (deletion)` | Tick deletion grace periods, execute phase 2 cascade | Cron (every 5 min) |
| `BackupPurgeWorker` | Purge deleted tenant data from backups within 30 days | Cron (daily) |
| `DnsAutomationWorker` | Handle async DNS record creation/removal with retries | Kafka consumer |
| `AbusePatternDetector` | Auto-suspension rules | Cron (every 5 min) |
| `DisposableEmailListUpdater` | Refresh disposable email domain list | Cron (weekly) |
| `CertManagerExpiryMonitor` | Alert if cert renewal lagging | Cron (daily) |
| `StatusPagePushPipeline` | Regenerate and push status page content | Cron (every 30 sec) |

---

## 10. Comparison to v5

| Aspect | v5 | v6 |
|---|---|---|
| Bounded contexts | ~30 | ~38 (added: tenants, billing/{plans, subs, quotas, providers}, data_lifecycle, abuse_prevention) |
| Middleware | auth, rate_limit, audit | + tenant_resolver (first in pipeline) |
| Database roles | musematic_app | + musematic_platform_staff (BYPASSRLS) |
| Kafka events | workspace_id, user_id | + tenant_id in every event |
| Frontend | single-tenant | tenant-aware, branding per tenant, tenant switcher |
| Workers | ~10 | ~17 (added 7 SaaS-specific) |
| Vault paths | platform-scoped | platform + tenant-scoped |
