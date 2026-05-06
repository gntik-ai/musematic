# UPD-054 — Data Model

UPD-054 is a test-suite extension. It introduces **no new database tables, no Alembic migrations, no new Kafka topics, no new Vault paths, no new MinIO buckets, no new Helm values**. This document inventories the brownfield models the journey tests touch and the in-process test-fixture data structures the new fixtures introduce.

## Brownfield models inspected by the suite

The journeys assert against state in the following existing tables and topics, all via the canonical public APIs (no direct DB writes):

### PostgreSQL — read-only inspection via the existing `db_session` fixture

| Table | Owner BC | Used by | Purpose |
|---|---|---|---|
| `tenants` | `tenants/` | J22, J24, J27, J31, J36 | Verify tenant row + status after admin API calls |
| `tenants_audit` | `tenants/` | J22, J27 | Verify audit-chain entries cross-reference the tenant id |
| `accounts_users` | `accounts/` | J22, J26, J33 | Verify first-admin invite + signup velocity counters |
| `accounts_audit` | `accounts/` | J26 | Suspension audit record |
| `workspaces` | `workspaces/` | J23, J31 | Quota counter snapshots |
| `subscriptions` | `billing/subscriptions` | J28, J30, J33, J34 | Subscription state + plan version pointer |
| `plans` / `plan_versions` | `billing/plans` | J30 | Plan v1 vs v2 attached subscriptions |
| `cost_events` | `analytics/` | J37 | Verify zero-cost on rejected Free attempts |
| `marketplace_agents` / `marketplace_visibility` | `marketplace/` | J25 | Visibility scope across tenants |
| `audit_chain_entries` | `audit/` | All | One whole-tail integrity check at session end |

### Kafka — read-only consumption via the existing `kafka_consumer` fixture

| Topic | Used by |
|---|---|
| `tenants.events` | J22, J27 |
| `accounts.events` | J22, J26, J33 |
| `billing.events` | J28, J30, J32, J33, J34 |
| `marketplace.events` | J25 |
| `policy.gate.blocked` | J23, J37 |

### Vault — read-only via the existing `SecretProvider`

| Path | Read by |
|---|---|
| `secret/data/musematic/dev/billing/stripe/api-key` | `tests/e2e/fixtures/stripe.py` (test-mode key) |
| `secret/data/musematic/dev/billing/stripe/webhook-secret` | Same fixture, for replay-signature verification |
| `secret/data/musematic/dev/dns/hetzner/api-token` | `tests/e2e/fixtures/dns.py` (only when `RUN_J29=1`) |

### MinIO / S3 — read-only via `aioboto3` and the generic-S3 client envvars

| Bucket | Read by |
|---|---|
| `tenant-dpas` | J22 (verify uploaded DPA artefact) |
| `tenant-data-exports` | J27 (verify export artefact in phase 1) |
| `marketplace-artifacts` | J25 (verify approved-agent payload) |

## In-process test-fixture data structures (NEW)

These dataclasses live in the new fixture modules and have no persistence. They exist for type-safe handoff between fixture and journey code.

### `tests/e2e/fixtures/tenants.py`

```python
@dataclass(frozen=True)
class TestTenant:
    slug: str
    tenant_id: UUID
    plan: str            # "free" | "pro" | "enterprise"
    region: str          # "eu-central" by default
    primary_admin_email: str
    primary_admin_user_id: UUID | None  # None until first admin completes setup
    dns_records_observed: bool = False  # set after the propagation poll succeeds
    cleanup_token: str  # opaque handle returned by the admin API; required for teardown
```

Lifecycle: created by `provision_enterprise(slug, plan, region)` → yielded into the journey → destroyed on context exit by `_teardown_tenant(cleanup_token)`. Idempotent on teardown (404 from the admin API is treated as success — see R8).

### `tests/e2e/fixtures/users.py`

```python
@dataclass(frozen=True)
class TestUser:
    user_id: UUID
    tenant_slug: str
    email: str           # always under "@e2e.musematic-test.invalid" per R4
    role: str            # "tenant_admin" | "workspace_owner" | "member" | "viewer"
    mfa_enrolled: bool
    mfa_secret: str | None  # TOTP secret, captured for use by login helpers
    auth_token: str      # bearer JWT for the user; refreshed by the http_client fixture
```

### `tests/e2e/fixtures/stripe.py`

```python
@dataclass(frozen=True)
class TestStripeCustomer:
    stripe_customer_id: str   # cus_test_*
    workspace_id: UUID
    test_clock_id: str | None  # set when the journey opts into Stripe Test Clock
    last_payment_method_id: str | None

@dataclass(frozen=True)
class TestSubscription:
    stripe_subscription_id: str
    workspace_id: UUID
    plan_id: str
    plan_version: int
    status: str           # "trialing" | "active" | "past_due" | "canceled" ...
    period_start: datetime
    period_end: datetime
```

### `tests/e2e/fixtures/dns.py`

```python
@dataclass(frozen=True)
class TestDnsRecord:
    name: str             # e.g. "acme" or "acme.api"
    record_type: str      # "A" | "AAAA"
    value: str
    provider_record_id: str | None  # None for mock; Hetzner record id in live mode
    created_at: datetime
```

`MockDnsProvider` keeps these in an in-process `dict`; `LiveHetznerDnsProvider` resolves them via the Hetzner DNS API (the fixture mirrors `apps/control-plane/src/platform/tenants/dns_automation.py` from UPD-053 so the test surface matches the runtime surface).

## Cross-references to brownfield code

Every fixture imports public surfaces only:

| Fixture | Imports |
|---|---|
| `tenants.py` | `tests.e2e.fixtures.http_client.AuthenticatedAsyncClient`, `tests.e2e.fixtures.db_session.AsyncSession` (read-only) |
| `users.py` | `tests.e2e.fixtures.http_client`; the `accounts/router.py` signup endpoint |
| `stripe.py` | The `stripe>=11.0,<12` SDK; the `SecretProvider` re-exported through `platform.common.secret_provider`; `stripe-cli` invoked via `subprocess` |
| `dns.py` | When live: the existing `apps/control-plane/src/platform/tenants/dns_automation.py` for Protocol parity; never re-exported into the runtime |

## State transitions

The journey tests cover the documented state machines from each owning BC; this feature does NOT redefine any state machine. Authoritative diagrams live with their owning BCs:

- **Tenant lifecycle**: `specs/099-marketplace-scope/` and `specs/103-abuse-prevention/data-lifecycle.md` (UPD-051).
- **Subscription lifecycle**: `specs/105-billing-payment-provider/data-model.md` (UPD-052).
- **Cert lifecycle**: `docs/operations/wildcard-tls-renewal.md` (UPD-053).

The journey assertions verify that real state transitions match the documented ones; the assertions are tied to the audit-chain entries the BC emits at each transition.
