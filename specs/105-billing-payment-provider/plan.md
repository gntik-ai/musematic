# Implementation Plan: UPD-052 — Billing and Overage (PaymentProvider Abstraction + Stripe)

**Branch**: `105-billing-payment-provider` | **Date**: 2026-05-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/105-billing-payment-provider/spec.md`

## Summary

Turns the existing UPD-047 stub `PaymentProvider` Protocol into a real billing surface backed by Stripe — Subscriptions API for fixed-price plans, Usage Records for metered overage, Customer Portal for self-service card maintenance, Stripe Tax for EU IVA OSS, and a hardened webhook ingress with HMAC verification + dual-secret rotation + idempotency. Adds a 7-day failed-payment grace state machine that emits day-1/3/5 reminders via UPD-077 notifications and downgrades the workspace to Free on day 7 with a *flag-don't-delete* posture for over-cap resources. Extends the existing `billing/` BC — never reimplements quota-enforcement, overage-authorization storage, or audit-chain primitives that UPD-047/UPD-051/UPD-024 already own.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js 14+ App Router); no Go work — the `runtime-controller`, `reasoning-engine`, `sandbox-manager`, and `simulation-controller` Go satellites do not own billing logic, so the spec's "Python + Go interface" reduces to a Python Protocol surface that the satellites do not directly call (they hit the existing quota/usage REST surface owned by Python). This narrows the scope materially and is documented under `research.md` R6.
**Primary Dependencies (existing, reused)**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, redis-py 5.x async, APScheduler 3.x, opentelemetry-sdk 1.27+, hvac (Vault), shadcn/ui, TanStack Query v5, React Hook Form + Zod 3.x, next-intl, lucide-react.
**Primary Dependencies (NEW)**: `stripe>=11.0` (Python; pinned to a 2024 SDK that supports `apiVersion="2024-06-20"` request-level override for forward compat), `@stripe/stripe-js@^4` and `@stripe/react-stripe-js@^2` (frontend; PaymentElement-only — *not* legacy Card Element). No new Helm sub-charts.
**Storage**:
- **PostgreSQL** — 4 new tables via Alembic migration **114** (next monotonic id, ≤32 chars: `114_billing_stripe`):
  - `payment_methods` (tenant-scoped, RLS) — id/tenant_id/workspace_id (nullable for tenant-level Enterprise)/stripe_payment_method_id (UNIQUE)/brand/last4/exp_month/exp_year/is_default/created_at.
  - `invoices` (tenant-scoped, RLS) — id/tenant_id/subscription_id/stripe_invoice_id (UNIQUE)/invoice_number/amount_total/amount_subtotal/amount_tax/currency/status/period_start/period_end/issued_at/paid_at/pdf_url/metadata_json.
  - `processed_webhooks` — composite PK `(provider, event_id)`, `event_type`, `processed_at`. Platform-level (not tenant-scoped) because the same Stripe event can affect multiple tenants and the row is dedupe metadata only.
  - `payment_failure_grace` (tenant-scoped) — id/tenant_id/subscription_id/started_at/grace_ends_at/reminders_sent/last_reminder_at/resolved_at/resolution. Partial unique index `(subscription_id) WHERE resolved_at IS NULL` so only one open grace row per subscription.
  - **Brownfield finding (already on `subscriptions`)**: `payment_method_id`, `stripe_customer_id`, `stripe_subscription_id` columns exist from UPD-047 with NULL semantics — migration 114 adds the FK from `subscriptions.payment_method_id` to `payment_methods.id` (deferred so Stripe-stub rows can stay NULL). No DDL change to `plan_versions` (already carries `stripe_price_id` columns).
- **Vault** — 2 paths under the existing KV v2 `secret/data/musematic/{env}/billing/stripe/`: `api-key` (sk_live_/sk_test_) and `webhook-secret` (the *active* and *previous* signing secrets stored as JSON `{ "active": "...", "previous": "..." }` so the rotation window is honored without a config push).
- **Redis** — 2 new key namespaces:
  - `billing:webhook_lock:{event_id}` (TTL 60s, SET NX) — short-lived dedupe lock so concurrent webhook deliveries from the same event id never both run handlers; the durable record stays in `processed_webhooks`.
  - `billing:portal_session_ratelimit:{customer_id}` (sliding window, 10/h) — protects Stripe quotas for the Customer Portal endpoint.
- **Kafka** — 1 new topic `billing.events` (registered via Strimzi `KafkaTopic` CRD; partitions=3, replicas=3 in prod): emits `billing.subscription.created`, `billing.subscription.updated`, `billing.subscription.cancelled`, `billing.invoice.paid`, `billing.invoice.failed`, `billing.payment_method.attached`, `billing.payment_failure_grace.opened`, `billing.payment_failure_grace.resolved`, `billing.dispute.opened`. The existing `accounts.events`/`workspaces.events`/`data_lifecycle.events` topics are unaffected.
- **S3** — none.
**Testing**: pytest 8.x + pytest-asyncio (per-BC unit + integration, ≥95% coverage rule 14), `tests/e2e/suites/billing/` (rule 25 — 6+ E2E tests; user input lists 10), Playwright + axe (rule 28 a11y for the 6 new frontend pages), Vitest + RTL (frontend). Stripe-test-mode-only in CI; the kind cluster journey tests use the Stripe public test environment behind a network egress allowlist (no test mocks of webhook signatures — real signed events from `stripe trigger`).
**Target Platform**: Existing Helm umbrella chart at `deploy/helm/platform/`. The existing `control-plane` sub-chart gains a new env-var family (`BILLING_STRIPE_*`, `BILLING_PROVIDER`, `BILLING_STRIPE_API_VERSION`). Production ingress already routes `/api/webhooks/*` to the control-plane Service; no new Ingress object is required, but rule 15 (separation of public webhooks vs internal API) is observed by adding a NetworkPolicy that allows the webhook path egress from the Stripe Webhooks IP allowlist only.
**Project Type**: Web service (Python control plane + Next.js frontend; no Go). Single bounded context extension: `billing/providers/stripe/`, `billing/webhooks/`, `billing/payment_methods/`, `billing/invoices/`, `billing/payment_failure_grace/`.
**Performance Goals**:
- Upgrade flow (Free → Pro, including SCA): ≤ 3 min p95 (SC-001).
- Webhook handler end-to-end (signature verify → handler complete → idempotency row written): ≤ 5 s p95 at 50 events/min (SC-003).
- Quota change visible after upgrade webhook: ≤ 60 s p95 (SC-002).
- Day-7 downgrade tick: within 1 hour of `grace_ends_at` (SC-005).
- Customer Portal session creation: ≤ 1 s p95.
- Invoice list page: ≤ 1 s p95 (server-rendered, indexed `(tenant_id, period_end DESC)`).
**Constraints**:
- **PCI scope SAQ-A only** — card data NEVER touches our servers (rule 11 secrets-in-LLM-context analogue for PII; PaymentElement+SetupIntent on the frontend, server only ever sees `pm_*` ids).
- **Webhook signature verification mandatory** — dual-secret window for rotation (active + previous), 401 + security-event log on failure, alert when ≥10 failures/15 min (rule 35 anti-enumeration analogue: don't leak which secret was tried).
- **Idempotency** — `(provider, event_id)` PK in `processed_webhooks` plus a Redis 60-s lock for the in-flight window. Atomic upsert on `subscriptions` + `payment_methods` rows so webhook race with API-call wins are eventually consistent.
- **Free hard cap preserved** — even with a card on file, Free workspaces never produce a Stripe charge (rule 25 — Free is hard-capped, never paused-with-authorize). The card record exists; the *pause-vs-block* branch is the existing UPD-047 quota-enforcer's `plan.allows_overage` flag.
- **Stripe API version pinning** — every outbound call sets the `Stripe-Version` header (request-level override) instead of pinning the SDK; lets the SDK upgrade cleanly while keeping API behavior frozen.
- **Audit chain on every transition** — rule 9 + AD-18; per-event entry with `actor_id`, `tenant_id`, `subscription_id`, `stripe_event_id`, `from_status`, `to_status`. No card data, no full invoice payload (just amounts + ids).
- **Vault failure-closed** — when Vault is unreachable, the webhook endpoint returns 503 instead of fall back to env vars (rule 39); the upgrade endpoint also 503s rather than risk creating Stripe state without a verifiable signing secret.
- **HTTPS enforced for webhook** — TLS termination at the ingress; the FastAPI handler reads `request.url.scheme` defensively and refuses non-https in non-test environments (rule 49 hardening).
- **Rate limit on webhook** — 100 req/s per Stripe IP via NGINX Ingress annotations + a Redis token-bucket fallback at the FastAPI layer.
- **3DS / SCA delegation** — the platform never bypasses or disables SCA; the embedded PaymentElement orchestrates the challenge.
- **Stripe test mode in dev cluster** — settings flag (`BILLING_STRIPE_MODE=test|live`) gates every outbound call; CI fails loudly if a test-mode key is detected in a `BILLING_STRIPE_MODE=live` deployment (start-up validation).
- **Refunds out of self-service** — super-admin-only via Stripe dashboard; refund webhooks are still handled (`charge.refunded`) so local invoice rows reconcile.
**Scale/Scope**:
- ~6 new admin REST endpoints (workspace billing surface) + 1 public webhook ingress + 1 Customer Portal session creator. The existing UPD-047 quota/overage REST endpoints are reused unchanged.
- ~14 new Python modules under `billing/`: `providers/stripe/{client,customer,subscription,usage,portal,tax,webhook_signing}.py`, `webhooks/{router,handlers,idempotency}.py`, `payment_methods/{models,schemas,repository,service}.py`, `invoices/{models,schemas,repository,service,router}.py`, `payment_failure_grace/{models,service,grace_monitor}.py`. The existing `billing/providers/protocol.py` is extended (new methods added to the Protocol; the stub gets parity stubs).
- 6 new frontend pages: `(main)/workspaces/[id]/billing/{page,upgrade/page,portal/page,invoices/page,cancel/page}.tsx` and `(admin)/admin/tenants/[id]/billing/page.tsx`. The existing `(main)/workspaces/[id]/billing/overage-authorize/page.tsx` from UPD-047 stays unchanged (it already uses the `OverageAuthorizationsService`).
- 1 new Kafka topic. 4 new PostgreSQL tables. 2 new Redis key namespaces. 2 new Vault paths.

## Constitution Check

Mapped to the Constitution v1.3.0 principles I–XVI plus the audit-pass rules (29–50). Each gate gets a one-line verdict; gaps are tracked in **Complexity Tracking** below.

| Principle / Rule | Verdict | Notes |
|---|---|---|
| **I. Modular Monolith (Python control plane)** | ✅ | All new code lives under the existing `billing/` BC; no new top-level service. |
| **II. Go Reasoning Engine separate** | ✅ | No Go work; reasoning-engine doesn't own billing. The spec's "Python + Go interface" sentence is reduced to "Python Protocol; Go satellites consume billing state via the existing REST/Kafka surface." Documented in research R6. |
| **III. Dedicated data stores** | ✅ | PostgreSQL for relational state, Redis for short-lived locks/rate limits, Kafka for events. No new physical store. |
| **IV. No cross-boundary DB access** | ✅ | `billing/` only reads/writes its own tables plus the UPD-047 `subscriptions`/`plan_versions` rows that already belong to `billing/`. Audit chain access is via `AuditChainService` (UPD-024 service, not direct table). |
| **V. Append-only execution journal** | N/A | Not a workflow runtime feature. |
| **VI. Policy is machine-enforced** | ✅ | Free hard-cap rule + overage authorization both enforced server-side via the existing UPD-047 quota engine; this feature only feeds it the `plan.allows_overage` flag. |
| **VII. Simulation isolation** | N/A | |
| **VIII. FQN addressing** | N/A | |
| **IX. Zero-trust default visibility** | ✅ | Billing endpoints require workspace-membership (`owner` or `admin`); admin-tenant view requires `platform_admin`; webhook endpoint requires only HMAC signature (no auth header). |
| **X. GID correlation** | ✅ | Billing audit/Kafka envelopes carry the existing correlation context primitives. |
| **XI. Secrets never in LLM context** | ✅ | Webhook payloads, card data, and Stripe API keys are excluded from any LLM-bound serialization (no `__repr__`/log emission of secrets). |
| **XII. Task plans persisted** | N/A | |
| **XIII. Attention pattern** | N/A | |
| **XIV. A2A** | N/A | |
| **XV. MCP** | N/A | |
| **XVI. Generic S3** | N/A | No object storage used. |
| **Rule 9 audit chain integrity** | ✅ | `AuditChainService.append()` invoked on every billing transition with non-sensitive metadata (FR-A2). |
| **Rule 11 SecretProvider only** | ✅ | Stripe API key + webhook secret loaded via the existing `SecretProvider` interface (rule 39); no env-var fallback. |
| **Rule 14 ≥95% coverage** | ✅ | Core service modules unit-tested with stub provider; webhook handlers + Stripe integration paths in coverage omit list because they require live Stripe events (research R5). |
| **Rule 15 BC boundary** | ✅ | Webhooks are a public ingress under `billing/webhooks/`, kept separate from `/api/v1/*` admin/user routes. |
| **Rule 24 audit dashboard** | ✅ | New `billing.yaml` Grafana dashboard at `deploy/helm/observability/templates/dashboards/`. |
| **Rule 25 E2E coverage** | ✅ | 10 E2E tests under `tests/e2e/suites/billing/` (user input enumeration). |
| **Rule 28 a11y** | ✅ | All 6 new frontend pages registered in `apps/web/tests/a11y/audited-surfaces.ts`. |
| **Rule 33 2PA** | ✅ | Subscription cancellation does NOT require 2PA (single-owner action); but force-downgrade by super admin DOES (rule 33; uses existing 2PA primitives). |
| **Rule 35 anti-enumeration** | ✅ | Webhook 401 response is identical regardless of which secret variant failed; portal session errors don't disclose whether the customer record exists. |
| **Rule 38 SecretProvider Vault failure closed** | ✅ | Webhook + upgrade endpoints 503 on Vault unavailability. |
| **Rule 39 Vault paths only** | ✅ | `secret/data/musematic/{env}/billing/stripe/{api-key,webhook-secret}` per Vault layout convention. |
| **Rule 49 outage independence** | ✅ | Webhook handler does NOT block on the Notifications BC — it persists state and emits a Kafka event; UPD-077 consumes asynchronously. The grace monitor does the same: it writes the grace row and emits, the notifier subscribes. |
| **Rule 50 mock LLM in creator previews** | N/A | |

**Constitution Check verdict**: PASS. No principle violations; one *narrowing* of the user input ("PaymentProvider Python + Go interface") to "Python only" is justified in the Complexity Tracking table.

## Project Structure

### Documentation (this feature)

```text
specs/105-billing-payment-provider/
├── plan.md                      # This file
├── research.md                  # Phase 0 output — 8 decisions
├── data-model.md                # Phase 1 output — 4 new tables + Subscriptions FK
├── quickstart.md                # Phase 1 output — Stripe test-mode operator runbook
├── contracts/
│   ├── billing-events-kafka.md
│   ├── stripe-webhook-rest.md
│   ├── workspace-billing-rest.md
│   ├── customer-portal-rest.md
│   ├── invoices-rest.md
│   └── tenant-billing-admin-rest.md
├── checklists/
│   └── requirements.md
└── tasks.md                     # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
apps/control-plane/
├── migrations/versions/
│   └── 114_billing_stripe.py
├── src/platform/billing/
│   ├── providers/
│   │   ├── protocol.py                  # EXTEND with charge_overage,
│   │   │                                #  create_customer_portal_session,
│   │   │                                #  verify_webhook_signature,
│   │   │                                #  handle_webhook_event
│   │   ├── stub_provider.py             # EXTEND with new method stubs
│   │   ├── factory.py                   # NEW — selects stripe|stub
│   │   └── stripe/
│   │       ├── __init__.py
│   │       ├── client.py                # SDK init + retry + Stripe-Version header
│   │       ├── customer.py              # create/retrieve customer
│   │       ├── subscription.py          # create/update/cancel
│   │       ├── usage.py                 # report_usage (Usage Records API)
│   │       ├── portal.py                # Customer Portal session
│   │       ├── tax.py                   # Stripe Tax wiring
│   │       ├── webhook_signing.py       # dual-secret HMAC verify
│   │       └── provider.py              # StripePaymentProvider (composes above)
│   ├── webhooks/
│   │   ├── __init__.py
│   │   ├── router.py                    # FastAPI APIRouter
│   │   ├── idempotency.py               # processed_webhooks repo
│   │   └── handlers/
│   │       ├── subscription.py          # *.created/updated/deleted/trial_will_end
│   │       ├── invoice.py               # invoice.payment_succeeded/failed
│   │       ├── payment_method.py        # payment_method.attached
│   │       ├── dispute.py               # charge.dispute.created
│   │       └── registry.py              # event_type → handler dispatch
│   ├── payment_methods/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   └── service.py
│   ├── invoices/
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── router.py
│   ├── payment_failure_grace/
│   │   ├── models.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── grace_monitor.py             # APScheduler cron — daily reminder + day-7 downgrade
│   └── events.py                        # billing.events Kafka envelopes
├── tests/unit/billing/
│   ├── test_stripe_provider.py
│   ├── test_webhook_signing.py
│   ├── test_webhook_idempotency.py
│   ├── test_handlers_subscription.py
│   ├── test_handlers_invoice.py
│   ├── test_handlers_payment_method.py
│   ├── test_handlers_dispute.py
│   ├── test_payment_failure_grace.py
│   ├── test_grace_monitor.py
│   ├── test_invoices_service.py
│   └── test_payment_methods_service.py
└── tests/integration/billing/
    └── test_*.py                        # skip-marked scaffolds (live-Stripe-needed)

apps/web/
├── app/(main)/workspaces/[id]/billing/
│   ├── page.tsx                         # EXTEND existing UPD-047 page
│   ├── upgrade/page.tsx                 # NEW — Stripe PaymentElement
│   ├── portal/page.tsx                  # NEW — server-redirect to Customer Portal
│   ├── invoices/page.tsx                # NEW — invoice list
│   └── cancel/page.tsx                  # NEW — cancel + reason
├── app/(admin)/admin/tenants/[id]/billing/page.tsx   # NEW
├── components/features/billing-stripe/
│   ├── UpgradeForm.tsx                  # NEW — embeds PaymentElement
│   ├── PaymentMethodCard.tsx
│   ├── InvoiceTable.tsx
│   ├── CancelForm.tsx
│   └── PortalRedirect.tsx
├── lib/api/billing-stripe.ts            # NEW — typed REST client
├── lib/hooks/use-billing-stripe.ts      # NEW — TanStack Query hooks
└── tests/a11y/audited-surfaces.ts       # EXTEND — 6 new entries

deploy/helm/control-plane/templates/
└── networkpolicy-stripe-webhook.yaml    # NEW — egress allowlist for webhook source IPs

deploy/helm/observability/templates/dashboards/
└── billing.yaml                         # NEW — Grafana dashboard (rule 24)

tests/e2e/suites/billing/
├── test_upgrade_to_pro.py               # J28
├── test_overage_authorization_flow.py   # J28
├── test_payment_failure_grace_then_downgrade.py    # J28
├── test_payment_recovery.py             # J28
├── test_cancellation_period_end.py      # J28
├── test_reactivation_during_cancellation_pending.py  # J34
├── test_webhook_idempotency.py          # J32
├── test_trial_conversion.py             # J33
├── test_free_card_no_overage.py
└── test_dispute_auto_suspend.py

tests/e2e/journeys/
├── test_j28_billing_lifecycle.py        # NEW skip-marked scaffold
├── test_j32_webhook_idempotency.py      # NEW skip-marked scaffold
├── test_j33_trial_to_paid_conversion.py # NEW skip-marked scaffold
└── test_j34_cancellation_reactivation.py # NEW skip-marked scaffold
```

**Structure Decision**: Single-BC extension under `apps/control-plane/src/platform/billing/`, frontend pages under the existing `(main)`/`(admin)` route groups, no new Helm sub-chart. The existing UPD-047 `billing/providers/protocol.py` is the seam — `StripePaymentProvider` is the *first real* concrete impl, and the stub keeps parity for unit tests.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **Narrowing the spec's "Python + Go interface" to Python-only** | The Go satellites (`runtime-controller`, `reasoning-engine`, `sandbox-manager`, `simulation-controller`) consume billing state through the existing REST quota surface and Kafka usage events; none of them call Stripe directly or need to issue charges. Adding a Go `PaymentProvider` interface in lockstep with the Python one would force the satellites to import a Stripe SDK they will never use, doubling the surface area for no functional benefit. | Adding a parallel Go interface "for symmetry" would: (a) violate Principle II (the satellites stay narrow), (b) require a Stripe Go SDK dependency in services that have no business calling Stripe, and (c) leave the Go interface unimplemented for the foreseeable future since no Go-side caller exists. Documented in research R6. |
| **`processed_webhooks` is platform-level (not tenant-scoped)** | A single Stripe event id is unique across the whole platform; tenant-scoping the dedupe table would force every webhook handler to first parse the payload to extract the tenant id, defeating the purpose of "verify-then-deduplicate-then-handle." | Making the table tenant-scoped would require: (a) parsing the payload to determine tenant before dedupe, (b) duplicate handlers if the same event affected multiple tenants. Standard SaaS pattern is platform-level dedupe. The row holds zero customer data — it's the event id and a timestamp. |
| **Redis 60-s lock on top of the durable PK** | Stripe sometimes delivers the same event twice within milliseconds (the SDK's recommended practice notes this). The PK alone fails the second concurrent insert with an integrity error mid-handler, leaving partial side effects. The Redis lock makes the dedupe check atomic *before* handler dispatch. | Relying on the PK alone would surface as flaky integrity errors that are hard to distinguish from real bugs. The Redis lock is short-lived and free-on-failure (TTL = 60s). |

---

*Phases 0 (research) and 1 (data-model + contracts + quickstart) are emitted as siblings to this file. Phase 2 (tasks.md) is generated by `/speckit-tasks` and is intentionally not produced here.*
