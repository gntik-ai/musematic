# Tasks: UPD-052 — Billing and Overage (PaymentProvider Abstraction + Stripe)

**Input**: Design documents from `/specs/105-billing-payment-provider/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: TDD scaffolds for the unit-tested modules and skip-marked integration/E2E test files are included per Constitution rule 25 (E2E coverage) and rule 14 (≥95% unit coverage). Live-Stripe paths follow the omit-list precedent established in UPD-051.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US6); foundational/setup/polish tasks omit it
- Each task lists the exact file path

## Path Conventions

- Backend: `apps/control-plane/src/platform/billing/...`, `apps/control-plane/migrations/versions/...`, `apps/control-plane/tests/{unit,integration}/billing/...`
- Frontend: `apps/web/app/{(main),(admin)}/...`, `apps/web/components/features/billing-stripe/...`, `apps/web/lib/{api,hooks}/...`
- Helm: `deploy/helm/{control-plane,observability}/...`
- E2E: `tests/e2e/{suites,journeys}/billing/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the new dependency, configure secrets layout, and document Stripe Dashboard prerequisites.

- [X] T001 Add `stripe>=11.0,<12` to `apps/control-plane/pyproject.toml` `[project] dependencies` (alphabetical order). Run `pip install -e .[dev]` to refresh the lockfile entry locally; CI will resolve from the same constraint.
- [X] T002 [P] Add `@stripe/stripe-js@^4` and `@stripe/react-stripe-js@^2` to `apps/web/package.json` `dependencies`. Run `pnpm install` and commit `pnpm-lock.yaml`.
- [X] T003 [P] Add the new env-var family (`BILLING_PROVIDER`, `BILLING_STRIPE_MODE`, `BILLING_STRIPE_API_VERSION`, `BILLING_STRIPE_PUBLISHABLE_KEY`, `BILLING_STRIPE_WEBHOOK_IP_ALLOWLIST`, `BILLING_PORTAL_RETURN_URL_ALLOWLIST`) to `apps/control-plane/src/platform/common/config.py` under a new `BillingStripeSettings` class with rule-37 inline `description=` annotations; expose it as `PlatformSettings.billing_stripe`.
- [X] T004 [P] Annotate the new env vars inline so `scripts/generate-env-docs.py` picks them up; regenerate `docs/configuration/environment-variables.md` and commit the diff.
- [X] T005 [P] Add the `billing.events` topic registration in `apps/control-plane/src/platform/common/events/topics.py` (or whichever module owns the topic registry); reuse the existing Strimzi `KafkaTopic` template under `deploy/helm/kafka/templates/kafka-topics.yaml` for `partitions: 3`, `replicas: 3 (prod) / 1 (dev)`, retention 7 days.
- [X] T006 Document the Stripe Dashboard one-time setup (price ids, webhook endpoint, Tax/IVA OSS, Customer Portal config, default API version) in `specs/105-billing-payment-provider/quickstart.md` (already drafted in Phase 1 of `/speckit-plan`; verify it survives `mkdocs build --strict` once linked from `docs/saas/`).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Migration, Vault layout, provider abstraction extension, Kafka envelopes — every user story phase depends on these.

⚠️ CRITICAL: no user-story work begins until Phase 2 is complete.

- [X] T007 Create Alembic migration `apps/control-plane/migrations/versions/114_billing_stripe.py` (revision id `114_billing_stripe`, ≤32 chars; `down_revision = "113_subproc_email_subs"`; `transactional_ddl = False`). Add the four tables (`payment_methods`, `invoices`, `processed_webhooks`, `payment_failure_grace`) per `data-model.md` with their indexes and RLS policies. Add the deferred FK on `subscriptions.payment_method_id`.
- [X] T008 [P] Create the SQLAlchemy ORM models for the four new tables under `apps/control-plane/src/platform/billing/{payment_methods,invoices,payment_failure_grace}/models.py` and `apps/control-plane/src/platform/billing/webhooks/models.py` (for `processed_webhooks`). Use the platform's `Base + UUIDMixin + TimestampMixin` pattern.
- [X] T009 [P] Extend the existing `PaymentProvider` Protocol in `apps/control-plane/src/platform/billing/providers/protocol.py` with the four new methods (`charge_overage`, `create_customer_portal_session`, `verify_webhook_signature`, `handle_webhook_event`) plus the supporting result dataclasses (`WebhookEvent`, `PortalSession`, `PaymentMethodInfo`, `OverageChargeReceipt`).
- [X] T010 [P] Add the parity stubs to `apps/control-plane/src/platform/billing/providers/stub_provider.py` so unit tests can keep importing the stub provider unchanged.
- [X] T011 Create the provider factory `apps/control-plane/src/platform/billing/providers/factory.py` that returns `StripePaymentProvider` when `settings.billing_provider == "stripe"` and `StubPaymentProvider` otherwise. Wire it into the existing `billing/dependencies.py` so the provider injection is configuration-driven.
- [X] T012 [P] Add the `billing.events` Kafka envelopes module `apps/control-plane/src/platform/billing/events.py` with Pydantic v2 payloads for the 9 event types in `contracts/billing-events-kafka.md`, plus a `publish_billing_event(producer, event_type, payload, correlation_ctx)` helper that mirrors the existing `publish_data_lifecycle_event` shape.
- [X] T013 [P] Add Vault path constants and a `StripeSecretsLoader` in `apps/control-plane/src/platform/billing/providers/stripe/secrets.py` that reads `secret/data/musematic/{env}/billing/stripe/{api-key,webhook-secret}` via the existing `SecretProvider`. Returns `{api_key: str, webhook_secrets: {active: str, previous: str | None}}`. Fail-closed on Vault unavailability (raise `BillingSecretsUnavailableError`).
- [X] T014 [P] Add billing Prometheus metrics to `apps/control-plane/src/platform/billing/metrics.py`: `billing_webhook_signature_failed_total`, `billing_webhook_processed_total{event_type, outcome}`, `billing_webhook_handler_duration_seconds{event_type}`, `billing_payment_failure_grace_open_count`, `billing_invoice_paid_total`, `billing_dispute_opened_total`.

**Checkpoint**: migration applied, models importable, provider factory wired, secrets loader available, Kafka envelopes ready, metrics registered. User-story phases can now begin in parallel.

---

## Phase 3: User Story 1 — Free → Pro upgrade with card (Priority: P1) 🎯 MVP

**Goal**: A Free workspace owner can upgrade to Pro via the embedded Stripe PaymentElement, complete SCA if requested, and have Pro quotas apply within 60 s of the `customer.subscription.created` webhook.

**Independent Test**: Stripe-test-mode upgrade end-to-end. Assert local subscription transitions to `active`, quotas raise to Pro, the first invoice carries `pdf_url` + `amount_tax`, and audit-chain entries cover every transition.

### Tests for User Story 1

- [X] T015 [P] [US1] Unit test `apps/control-plane/tests/unit/billing/test_stripe_provider.py` covering customer creation + payment-method attach + subscription create against a recorded canonical Stripe response set (no live calls — patch `stripe.Customer.create`, `stripe.PaymentMethod.attach`, `stripe.Subscription.create` with deterministic fixtures).
- [X] T016 [P] [US1] Unit test `apps/control-plane/tests/unit/billing/test_handlers_subscription.py` covering the `customer.subscription.created` handler from a fixture event payload — assert local row upsert + Kafka emission + audit-chain append.
- [X] T017 [P] [US1] Integration test scaffold (skip-marked) `apps/control-plane/tests/integration/billing/test_upgrade_flow.py` — requires `make dev-up` + Stripe CLI listener; verifies the full HTTP→webhook→quota flow.
- [X] T018 [P] [US1] E2E test `tests/e2e/suites/billing/test_upgrade_to_pro.py` (skip-marked until the kind cluster + Stripe test mode are wired in CI matrix).

### Implementation for User Story 1

- [X] T019 [P] [US1] Implement `apps/control-plane/src/platform/billing/providers/stripe/client.py` — Stripe SDK initializer with `Stripe-Version` header set per request, `asyncio.to_thread` wrapper, exponential-backoff retry for `RateLimitError` and `APIConnectionError`.
- [X] T020 [P] [US1] Implement `apps/control-plane/src/platform/billing/providers/stripe/customer.py` — `create_customer(tenant_id, email, metadata)` and `retrieve_customer(stripe_customer_id)`.
- [X] T021 [P] [US1] Implement `apps/control-plane/src/platform/billing/providers/stripe/subscription.py` — `create_subscription`, `update_subscription`, `cancel_subscription` with `automatic_tax: { enabled: true }` per research R7.
- [X] T022 [US1] Implement `apps/control-plane/src/platform/billing/providers/stripe/provider.py` — `StripePaymentProvider` composes the helpers above and implements the full `PaymentProvider` Protocol surface (depends on T019–T021).
- [X] T023 [P] [US1] Implement the `payment_methods` BC under `apps/control-plane/src/platform/billing/payment_methods/{schemas,repository,service}.py` per `data-model.md`. Service exposes `record_attached(stripe_pm_id, brand, last4, …)` and `set_default(payment_method_id)`.
- [X] T024 [P] [US1] Implement the `invoices` BC under `apps/control-plane/src/platform/billing/invoices/{schemas,repository,service}.py` per `data-model.md`. Service exposes `upsert_from_stripe(stripe_invoice)` (idempotent by `stripe_invoice_id`).
- [X] T025 [US1] Wire the `customer.subscription.created` handler in `apps/control-plane/src/platform/billing/webhooks/handlers/subscription.py` — upserts local subscription, sets payment_method_id from the embedded `default_payment_method`, emits `billing.subscription.created`, appends audit chain.
- [X] T026 [US1] Wire the `payment_method.attached` handler in `apps/control-plane/src/platform/billing/webhooks/handlers/payment_method.py` — calls `payment_methods.service.record_attached`, emits `billing.payment_method.attached`.
- [X] T027 [US1] Wire the `invoice.payment_succeeded` handler in `apps/control-plane/src/platform/billing/webhooks/handlers/invoice.py` (the on-paid branch) — calls `invoices.service.upsert_from_stripe`, emits `billing.invoice.paid`.
- [X] T028 [US1] Implement the upgrade endpoint `POST /api/v1/workspaces/{workspace_id}/billing/upgrade` in `apps/control-plane/src/platform/billing/router.py` (extend the existing UPD-047 router) per `contracts/workspace-billing-rest.md` — calls `StripePaymentProvider` to create customer (idempotent if already exists) + subscription, returns immediately with the `pending` status; the webhook flips to `active`.
- [X] T029 [P] [US1] Frontend: `apps/web/lib/api/billing-stripe.ts` — typed REST client for upgrade/cancel/reactivate/portal-session/list-invoices/get-invoice.
- [X] T030 [P] [US1] Frontend: `apps/web/lib/hooks/use-billing-stripe.ts` — TanStack Query hooks (`useUpgradeWorkspace`, `useCancelSubscription`, `useReactivateSubscription`, `usePortalSession`, `useInvoices`).
- [X] T031 [US1] Frontend: `apps/web/components/features/billing-stripe/UpgradeForm.tsx` — embeds `<Elements stripe={...}>` + `<PaymentElement />` from `@stripe/react-stripe-js`, RHF + Zod for billing-address fields, handles SCA via `stripe.confirmSetup` flow.
- [X] T032 [US1] Frontend: `apps/web/app/(main)/workspaces/[id]/billing/upgrade/page.tsx` — plan selector + `<UpgradeForm>` per `contracts/workspace-billing-rest.md`. Disabled with a 503-style banner when the API returns `stripe_unavailable`.
- [X] T033 [US1] Frontend: extend the existing `apps/web/app/(main)/workspaces/[id]/billing/page.tsx` to surface payment-method + recent-invoices sections; reuse `useBillingStripe` hooks.
- [X] T034 [P] [US1] Add `dataLifecycle`-style locale namespace `billing` to `apps/web/messages/en.json` covering all 6 new pages + the email-template strings; mirror to the 6 other locales (en values verbatim) per UPD-051 follow-up T100 precedent.

**Checkpoint**: User Story 1 is fully functional — a Free workspace can upgrade to Pro via the embedded card form, the webhook lands, the local state transitions, quotas apply.

---

## Phase 4: User Story 2 — Pro hits quota and authorizes overage (Priority: P1)

**Goal**: A Pro workspace at 100% of included minutes pauses the next execution, fires an "Authorize overage" notification, persists the authorization on click, resumes paused executions, and the end-of-period invoice carries the overage line item.

**Independent Test**: Drive a Pro workspace past included minutes; assert pause + notification + authorize → resume → metered usage reported to Stripe → invoice line item.

### Tests for User Story 2

- [X] T035 [P] [US2] Unit test `apps/control-plane/tests/unit/billing/test_overage_metered_reporting.py` — covers `StripePaymentProvider.report_usage` against fixture Stripe responses + the batched-vs-real-time decision logic.
- [X] T036 [P] [US2] Integration test scaffold (skip-marked) `apps/control-plane/tests/integration/billing/test_overage_authorization_flow.py`.
- [X] T037 [P] [US2] E2E test `tests/e2e/suites/billing/test_overage_authorization_flow.py` (skip-marked).

### Implementation for User Story 2

- [X] T038 [US2] Implement `apps/control-plane/src/platform/billing/providers/stripe/usage.py` — `report_usage(subscription_item_id, quantity, timestamp, idempotency_key)` per the Stripe Usage Records API; supports batched submission within rate limits.
- [X] T039 [US2] Wire the existing UPD-047 `OverageAuthorizationsService` to call `StripePaymentProvider.report_usage` when an authorization is open and the execution engine reports overage minutes (extend `apps/control-plane/src/platform/billing/quotas/overage.py`).
- [X] T040 [US2] Update the `customer.subscription.updated` handler in `apps/control-plane/src/platform/billing/webhooks/handlers/subscription.py` to capture `subscription_item.id` for the metered overage price so subsequent `report_usage` calls can find it.
- [X] T041 [P] [US2] Confirm the existing UPD-047 frontend page at `apps/web/app/(main)/workspaces/[id]/billing/overage-authorize/page.tsx` correctly surfaces the projected cost based on burn rate; if the existing page does not yet show a projected-cost preview, extend it to do so via a new `useOverageProjection` hook (no Stripe Elements involved here — this is platform-side math).

**Checkpoint**: Overage UX (Option C) functions end-to-end — pause → notification → authorize → resume → metered Stripe usage → end-of-period invoice line item.

---

## Phase 5: User Story 3 — Failed payment grace + downgrade (Priority: P1)

**Goal**: `invoice.payment_failed` opens a 7-day grace; reminders go out on day 1 / day 3 / day 5; on day 7 if not recovered, the workspace downgrades to Free with cleanup-flagging.

**Independent Test**: Trigger `invoice.payment_failed` → assert past_due + grace row + day-1 reminder. Fast-forward wall clock (CI) → day-7 downgrade → flagged resources.

### Tests for User Story 3

- [X] T042 [P] [US3] Unit test `apps/control-plane/tests/unit/billing/test_payment_failure_grace.py` covering `start_grace`, `tick_reminder` (parameterized at day-1/3/5), `resolve_payment_recovered`, `resolve_downgrade`.
- [X] T043 [P] [US3] Unit test `apps/control-plane/tests/unit/billing/test_grace_monitor.py` — covers the cron tick logic (which graces need a reminder, which need to fire the day-7 downgrade) using a frozen-clock fixture.
- [X] T044 [P] [US3] Integration test scaffold (skip-marked) `apps/control-plane/tests/integration/billing/test_payment_failure_grace_then_downgrade.py`.
- [X] T045 [P] [US3] E2E test `tests/e2e/suites/billing/test_payment_failure_grace_then_downgrade.py` (skip-marked).
- [X] T046 [P] [US3] E2E test `tests/e2e/suites/billing/test_payment_recovery.py` (skip-marked).

### Implementation for User Story 3

- [X] T047 [P] [US3] Implement `apps/control-plane/src/platform/billing/payment_failure_grace/repository.py` — `find_open_for_subscription`, `open(subscription_id)`, `tick_reminder(grace_id)`, `resolve(grace_id, resolution)`, `list_due_for_reminder(now)`, `list_due_for_expiry(now)`.
- [X] T048 [P] [US3] Implement `apps/control-plane/src/platform/billing/payment_failure_grace/service.py` — `start_grace(subscription_id)`, `resolve_payment_recovered(subscription_id)`, `resolve_downgrade(subscription_id)`, plus Kafka emission via `publish_billing_event`.
- [X] T049 [US3] Implement the APScheduler cron `apps/control-plane/src/platform/billing/payment_failure_grace/grace_monitor.py` — runs every 6 hours (configurable), calls `service.tick_reminders()` for day-1/3/5 and `service.tick_expiries()` for day-7. Wire the scheduler into the worker profile in `apps/control-plane/src/platform/main.py`.
- [X] T050 [US3] Wire the `invoice.payment_failed` handler in `apps/control-plane/src/platform/billing/webhooks/handlers/invoice.py` — calls `service.start_grace`, transitions subscription to `past_due`, emits `billing.invoice.failed` + `billing.payment_failure_grace.opened`.
- [X] T051 [US3] Update the `invoice.payment_succeeded` handler so that when an open grace exists for the subscription it calls `service.resolve_payment_recovered` (extends the T027 implementation).
- [X] T052 [US3] Implement the downgrade-to-Free helper `apps/control-plane/src/platform/billing/payment_failure_grace/downgrade.py` — flips the workspace's plan to Free, flags over-cap resources via the existing UPD-047 `flag_for_cleanup` interface (do NOT delete), emits `billing.payment_failure_grace.resolved` with `resolution=downgraded_to_free`.
- [X] T053 [P] [US3] Add UPD-077 notification template keys for the 3 grace reminders + the day-7 downgrade in `apps/control-plane/src/platform/notifications/service.py` `_NOTIFICATION_TEMPLATES` dict (6 locales: en/es/fr/de/ja/zh-CN). Template keys: `payment_failure_reminder_title/body` (parameterized by day-N) and `payment_downgraded_title/body`.
- [X] T054 [US3] Add a `BillingFailureGraceConsumer` in `apps/control-plane/src/platform/notifications/consumers/billing_failure_grace_consumer.py` that subscribes to `billing.events` and dispatches the day-N reminder and downgrade alerts via the existing `process_admin_alert` style. Register it in `main.py` next to the existing `ExportReadyConsumer`.

**Checkpoint**: 7-day grace state machine functions end-to-end — webhook opens grace, daily cron sends reminders, day-7 downgrades and flags resources.

---

## Phase 6: User Story 4 — Customer Portal self-service (Priority: P2)

**Goal**: Pro user clicks "Manage billing" → server creates a Stripe Customer Portal session → user updates card → webhook syncs new payment method.

**Independent Test**: Trigger portal-session creation, follow the redirect to Stripe (test mode), update test card via the Stripe-hosted UI, assert `payment_method.attached` webhook lands and the local default payment method updates.

### Tests for User Story 4

- [X] T055 [P] [US4] Unit test `apps/control-plane/tests/unit/billing/test_customer_portal.py` — covers session creation, return-URL allowlist validation, rate-limit behavior.
- [X] T056 [P] [US4] Integration test scaffold (skip-marked) `apps/control-plane/tests/integration/billing/test_customer_portal_session.py`.

### Implementation for User Story 4

- [X] T057 [P] [US4] Implement `apps/control-plane/src/platform/billing/providers/stripe/portal.py` — `create_session(customer_id, return_url)` calls `stripe.billing_portal.Session.create`.
- [X] T058 [US4] Implement the rate limiter `apps/control-plane/src/platform/billing/portal_rate_limit.py` using the existing Redis client (sliding window, key `billing:portal_session_ratelimit:{customer_id}`, window 1 hour, limit 10).
- [X] T059 [US4] Implement the workspace endpoint `POST /api/v1/workspaces/{workspace_id}/billing/portal-session` per `contracts/customer-portal-rest.md` — validates the return-url allowlist, calls the rate limiter, calls `StripePaymentProvider.create_customer_portal_session`, returns the URL, audit-logs the action without the URL.
- [X] T060 [US4] Frontend: `apps/web/components/features/billing-stripe/PortalRedirect.tsx` — triggers `usePortalSession` and on success uses `window.location.assign(portal_url)`; shows a clear loading state.
- [X] T061 [US4] Frontend: `apps/web/app/(main)/workspaces/[id]/billing/portal/page.tsx` — server-redirect orchestration page that calls the endpoint and redirects (the server component does the fetch; if Stripe is unavailable it renders a fallback "try again later" card).

**Checkpoint**: Customer Portal self-service works end-to-end.

---

## Phase 7: User Story 5 — Cancellation period-end + reactivation (Priority: P2)

**Goal**: Cancel marks `cancel_at_period_end=true`; user retains Pro features until period end; reactivation reverses the cancel; otherwise period-end downgrades to Free.

**Independent Test**: Submit cancellation → assert `cancellation_pending`. Reactivate → assert `active`. Otherwise let period end → assert `customer.subscription.deleted` flow downgrades to Free.

### Tests for User Story 5

- [X] T062 [P] [US5] Unit test `apps/control-plane/tests/unit/billing/test_cancel_reactivate.py` — covers cancel API + reactivate API + the `customer.subscription.deleted` handler against fixture events.
- [X] T063 [P] [US5] Integration test scaffold (skip-marked) `apps/control-plane/tests/integration/billing/test_cancellation_period_end.py`.
- [X] T064 [P] [US5] E2E test `tests/e2e/suites/billing/test_cancellation_period_end.py` (skip-marked).
- [X] T065 [P] [US5] E2E test `tests/e2e/suites/billing/test_reactivation_during_cancellation_pending.py` (skip-marked).

### Implementation for User Story 5

- [X] T066 [US5] Implement the cancel endpoint `POST /api/v1/workspaces/{workspace_id}/billing/cancel` per `contracts/workspace-billing-rest.md` — calls `StripePaymentProvider.cancel_subscription(at_period_end=True)`, transitions local status to `cancellation_pending`, persists reason+reason_text on the existing `subscriptions` row (or a new `cancellation_reasons` table if the column doesn't exist; check first), emits `billing.subscription.updated`.
- [X] T067 [US5] Implement the reactivate endpoint `POST /api/v1/workspaces/{workspace_id}/billing/reactivate` — calls `update_subscription(cancel_at_period_end=False)`, transitions local status to `active`. Returns 409 if the subscription has already passed `period_end`.
- [X] T068 [US5] Wire the `customer.subscription.deleted` handler in `apps/control-plane/src/platform/billing/webhooks/handlers/subscription.py` — transitions local status to `canceled`, downgrades the workspace to Free, applies the same flag-don't-delete behavior as the day-7 downgrade (reuse `payment_failure_grace/downgrade.py`).
- [X] T069 [P] [US5] Frontend: `apps/web/components/features/billing-stripe/CancelForm.tsx` — RHF + Zod (reason enum from contracts), confirmation dialog before submission, surfaces the period-end date in the success state.
- [X] T070 [US5] Frontend: `apps/web/app/(main)/workspaces/[id]/billing/cancel/page.tsx` — wraps `CancelForm` and the reactivate call-to-action when `cancellation_pending`.

**Checkpoint**: Cancellation + reactivation lifecycle covered.

---

## Phase 8: User Story 6 — Free workspace stores card without overage (Priority: P2)

**Goal**: Free user adds a card on file; future upgrade pre-fills; Free overage attempts remain hard-capped (no Stripe charge).

**Independent Test**: Free user adds card via Stripe Elements → confirms card stored. Push usage past Free cap → execution blocked (not paused), no Stripe charge created.

### Tests for User Story 6

- [X] T071 [P] [US6] Unit test `apps/control-plane/tests/unit/billing/test_free_card_no_overage.py` — assert that when a Free workspace has a payment_methods row, the quota engine still returns `BLOCKED` (not `OVERAGE_REQUIRED`) on cap exhaustion.
- [X] T072 [P] [US6] E2E test `tests/e2e/suites/billing/test_free_card_no_overage.py` (skip-marked).

### Implementation for User Story 6

- [X] T073 [US6] Add a "store card on file" endpoint or extend the upgrade endpoint to accept `target_plan_slug=free_with_card` (pick the simpler shape during implementation; document in commit). The endpoint creates a Stripe customer (if absent), attaches the payment method via SetupIntent (no subscription created).
- [X] T074 [US6] Frontend: extend `UpgradeForm.tsx` to support a "save card without upgrading" mode triggered from the Free billing page — same `<PaymentElement>` instance, different submit handler that calls the store-card-on-file endpoint instead of upgrade.

**Checkpoint**: Free-with-card UX works without ever producing a Stripe charge.

---

## Phase 9: Cross-cutting webhook ingress + idempotency

**Purpose**: Centralized FastAPI ingress, signature verification with dual-secret rotation, the two-layer idempotency check, and the dispatch registry. Lands as a single phase because the surface is shared by all user stories.

- [X] T075 [P] Implement `apps/control-plane/src/platform/billing/providers/stripe/webhook_signing.py` — `verify(payload_bytes, signature_header, secrets)` per research R2. Falls back to `previous` on mismatch. Raises `SignatureError` on both-fail. Unit test included in T076.
- [X] T076 [P] Unit test `apps/control-plane/tests/unit/billing/test_webhook_signing.py` — uses `stripe.Webhook.construct_event` against canonical fixture payloads, covers active-only, previous-only, both-rotation, and tampered-body cases.
- [X] T077 [P] Implement `apps/control-plane/src/platform/billing/webhooks/idempotency.py` — `WebhookIdempotency` class with `acquire_lock(event_id)` (Redis SET NX EX 60), `is_processed(event_id)` (DB SELECT), and `mark_processed(event_id, event_type)` (DB INSERT). Two-layer pattern from research R3.
- [X] T078 [P] Unit test `apps/control-plane/tests/unit/billing/test_webhook_idempotency.py` — covers lock-acquire success/failure, duplicate detection, and the acquire-then-already-processed race.
- [X] T079 Implement `apps/control-plane/src/platform/billing/webhooks/handlers/registry.py` — `dispatch(event)` looks up `event_type → handler` and runs the handler. Unknown event types return `{"status": "ignored"}`. Handler exceptions propagate (the router converts to 500 to force Stripe retry).
- [X] T080 Implement `apps/control-plane/src/platform/billing/webhooks/router.py` — FastAPI APIRouter with `POST /api/webhooks/stripe`. Loads secrets via `StripeSecretsLoader` (T013), verifies signature (T075), acquires lock (T077), checks dedupe (T077), dispatches (T079), inserts idempotency row, returns 200/401/503 per `contracts/stripe-webhook-rest.md`. Register on the main FastAPI app and explicitly EXCLUDED from JWT auth middleware.
- [X] T081 [P] Add NetworkPolicy `deploy/helm/control-plane/templates/networkpolicy-stripe-webhook.yaml` — allows ingress from Stripe Webhooks IP allowlist only on the webhook path; egress to Stripe API CIDR allowed.
- [X] T082 [P] Integration test scaffold (skip-marked) `apps/control-plane/tests/integration/billing/test_webhook_ingress_signature.py` — drives a real signed event from `stripe trigger` against the kind cluster.
- [X] T083 [P] E2E test `tests/e2e/suites/billing/test_webhook_idempotency.py` (skip-marked) — sends the same Stripe event id twice and asserts only one set of side effects.

---

## Phase 10: Cross-cutting Stripe Tax integration

- [X] T084 [P] Implement `apps/control-plane/src/platform/billing/providers/stripe/tax.py` — thin module that documents the `automatic_tax: { enabled: true }` parameter that the subscription/invoice helpers must include. Houses the tax-line-item parser used by `invoices.service.upsert_from_stripe` to break down `amount_tax`.
- [X] T085 [P] Update `quickstart.md` § Stripe Dashboard configuration with the Stripe Tax + IVA OSS step (already drafted; verify operator runbook).

---

## Phase 11: Cross-cutting `invoices` REST surface

- [X] T086 [P] Implement `apps/control-plane/src/platform/billing/invoices/router.py` — endpoints from `contracts/invoices-rest.md`: list, get, pdf-redirect (with Stripe `Invoice.retrieve` refresh on URL expiry).
- [X] T087 [P] Frontend: `apps/web/components/features/billing-stripe/InvoiceTable.tsx` — table with downloadable PDFs.
- [X] T088 [US1] Frontend: `apps/web/app/(main)/workspaces/[id]/billing/invoices/page.tsx` — wraps `InvoiceTable` with cursor pagination via `useInvoices`.

---

## Phase 12: Cross-cutting Enterprise tenant admin

- [X] T089 [P] Implement the tenant admin endpoints from `contracts/tenant-billing-admin-rest.md` in `apps/control-plane/src/platform/billing/admin_router.py` (extend the existing UPD-047 admin router). The 2PA-gated `force-suspend` and `force-downgrade` endpoints reuse `TwoPersonApprovalService`.
- [X] T090 [P] Frontend: `apps/web/app/(admin)/admin/tenants/[id]/billing/page.tsx` — Enterprise tenant billing view showing subscription, payment method, recent invoices, force-suspend/force-downgrade buttons (the 2PA flow uses the existing UPD-039 / feature 086 2PA tray).

---

## Phase 13: Cross-cutting `charge.dispute.created` handler

- [X] T091 [P] Implement the dispute handler `apps/control-plane/src/platform/billing/webhooks/handlers/dispute.py` — auto-suspends the subscription, emits `billing.dispute.opened`, dispatches a high-urgency super-admin notification. Per spec edge cases.
- [X] T092 [P] Unit test `apps/control-plane/tests/unit/billing/test_handlers_dispute.py`.
- [X] T093 [P] E2E test `tests/e2e/suites/billing/test_dispute_auto_suspend.py` (skip-marked).

---

## Phase 14: Polish & Cross-Cutting Concerns

- [X] T094 [P] Add audit-chain entries on every billing transition by extending the existing `AuditChainService.append` calls in each handler/service. Each entry payload SHOULD carry `actor_id` (when known), `tenant_id`, `subscription_id`, `stripe_event_id`, and `from_status`/`to_status` — never card data.
- [X] T095 [P] Add the Grafana dashboard `deploy/helm/observability/templates/dashboards/billing.yaml` (rule 24) with panels for: webhook signature failures, webhook handler latency p50/p95/p99, open grace count, invoices paid per day, disputes opened per week, downgrade-to-free count.
- [X] T096 [P] Register the 8 new frontend surfaces in `apps/web/tests/a11y/audited-surfaces.ts` (rule 28): `billing-overview`, `billing-upgrade`, `billing-portal`, `billing-invoices`, `billing-cancel`, `admin-tenant-billing`, plus the existing `overage-authorize`. The 8th is the public store-card variant if the implementation in T073 chooses a separate route.
- [X] T097 [P] Mirror the new `billing` locale keys (T034) to the 6 non-English locale catalogs (de.json, es.json, fr.json, it.json, ja.json, zh-CN.json) per UPD-051 follow-up T100 precedent (English values verbatim; translator pickup later).
- [X] T098 [P] Add the J28 / J32 / J33 / J34 journey skip-marked scaffolds: `tests/e2e/journeys/test_j28_billing_lifecycle.py`, `test_j32_webhook_idempotency.py`, `test_j33_trial_to_paid_conversion.py`, `test_j34_cancellation_reactivation.py`. Each conforms to the journey-structure validator (`JOURNEY_ID`, `TIMEOUT_SECONDS`, markers, ≥10 step blocks once unskipped).
- [X] T099 [P] Register J28/J32/J33/J34 in `tests/e2e/journeys/__init__.py` `BILLING_JOURNEYS` registry (new constant) and add `make e2e-j28`, `make e2e-j32`, `make e2e-j33`, `make e2e-j34` targets to `tests/e2e/Makefile` plus the matching PHONY entries.
- [X] T100 [P] Add the Helm values for billing under `deploy/helm/control-plane/values.yaml` (defaults: `provider: stub`, `mode: test`) and override in `deploy/helm/platform/values.dev.yaml` (`provider: stripe`, `mode: test`) and `deploy/helm/platform/values.prod.yaml` (`provider: stripe`, `mode: live`). Run `helm-docs --chart-search-root=deploy/helm` and `python scripts/aggregate-helm-docs.py --output docs/configuration/helm-values.md` to refresh the docs.
- [X] T101 [P] Add operator documentation pages: `docs/saas/billing-stripe.md` (high-level architecture), `deploy/runbooks/billing/{webhook-signature-failures,grace-monitor-paused,stripe-rotation,dispute-response}.md` (4 runbooks under `deploy/runbooks/billing/`).
- [X] T102 [P] Add the cold-storage scan extension hook to `tools/verify_audit_chain.py` (no change required if existing UPD-051 tool already runs platform-wide; confirm behavior). Ensure the billing audit entries are inside the chain walk.
- [X] T103 Final coverage sweep: ensure `pytest --cov=src/platform/billing --cov-fail-under=95` passes locally for the unit-tested modules. If specific framework-glue paths drop the package below 95%, add them to the `[tool.coverage.run] omit` list in `apps/control-plane/pyproject.toml` with the same comment-style precedent as UPD-051 (rule 14 follow-up policy).
- [X] T104 Mark the spec's acceptance criteria checklist as complete by editing `specs/105-billing-payment-provider/spec.md` once every task above is closed.

---

## Dependencies

```text
Phase 1 (Setup) ──────────────► Phase 2 (Foundational)
                                       │
              ┌────────────────┬───────┼───────┬───────────────┬───────────────┐
              ▼                ▼       ▼       ▼               ▼               ▼
       Phase 3 (US1) ─► Phase 9 (Webhook ingress)        Phase 10 (Tax)   Phase 13 (Dispute)
              │                │
              │                │ ◄── Phase 9 is a hard prerequisite for Phases 4, 5, 6, 7, 13
              │                │
              ▼                ▼
       Phase 4 (US2)    Phase 5 (US3)    Phase 6 (US4)    Phase 7 (US5)    Phase 8 (US6)
              │                │                │                │                │
              └────────────────┴────────────────┼────────────────┴────────────────┘
                                                ▼
                            Phase 11 (Invoices REST)  Phase 12 (Enterprise admin)
                                                │
                                                ▼
                                       Phase 14 (Polish)
```

**Hard prerequisites** (cannot start until predecessor is complete):
- Phase 2 blocks every later phase.
- Phase 9 (webhook ingress + idempotency) blocks every webhook handler in Phases 3–8 and Phase 13.
- T103 (final coverage sweep) blocks T104 (spec acceptance criteria check-off).

**Soft prerequisites** (can run in parallel but make more sense sequenced):
- Phase 5 (US3 grace) is logically tested after Phase 3 (US1 upgrade) is working — you need an `active` subscription to fail.
- Phase 7 (US5 cancel) is logically tested after Phase 3 — same reason.

## Parallel execution opportunities

Within Phase 2 (after T007 migration applies):
- T008, T009, T010, T012, T013, T014 are all `[P]` — six developers can work in parallel.

Within Phase 3 (US1):
- T015–T018 (tests) parallel with each other.
- T019–T021 (Stripe helpers) parallel with each other.
- T023, T024 (payment_methods + invoices BCs) parallel with each other.
- T029, T030 (frontend client + hooks) parallel with each other.
- T034 (i18n) parallel with frontend pages.

Across phases, after Phase 9 lands:
- Phases 4, 5, 6, 7, 8, 13 are independently testable user-story slices and can be developed in parallel by different devs.

## Implementation strategy

**MVP scope** (smallest deployable slice that delivers user value): **Phase 1 + Phase 2 + Phase 9 + Phase 3 (US1)**. With this slice, a Free workspace can upgrade to Pro and the platform charges the card. No grace, no overage UX, no portal — just the upgrade path.

**Increment 2**: + Phase 5 (US3) + Phase 11 (invoices REST). Now failed payments don't silently break Pro workspaces, and users can see their invoices.

**Increment 3**: + Phase 4 (US2) + Phase 7 (US5). Overage UX + cancellation cycle. This brings the feature to "complete revenue capture and self-service lifecycle."

**Increment 4**: + Phase 6 (US4) + Phase 8 (US6) + Phase 12 (Enterprise admin) + Phase 13 (dispute) + Phase 14 (polish). Round out the operator-facing and edge-case surfaces.

This strategy lets the team merge Increment 1 to main quickly (all CI gates green), then layer the remaining increments without ever leaving main in a half-broken state.

## Format validation

All 104 tasks above use the strict checklist format (`- [ ] T### [P?] [Story?] description with file path`). Setup, Foundational, and cross-cutting/polish tasks omit the story label per the rules; user-story phases (3–8) carry their `[US1]`–`[US6]` label; parallel-safe tasks carry `[P]`.
