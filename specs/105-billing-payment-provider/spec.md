# Feature Specification: Billing and Overage — PaymentProvider Abstraction + Stripe (UPD-052)

**Feature Branch**: `105-billing-payment-provider`
**Created**: 2026-05-04
**Status**: Draft
**Input**: User description: UPD-052 turns the stub PaymentProvider plumbing introduced by UPD-047 into a real billing surface backed by Stripe — including subscriptions, metered overage, webhooks, Customer Portal, invoices, failed-payment grace, EU tax, and the overage-authorize UX.

## Brownfield Context

UPD-047 shipped the data + business plumbing for plans, plan versions, subscriptions, usage records, and overage authorizations, plus columns for `payment_method_id`, `stripe_customer_id`, and `stripe_subscription_id`. None of those columns are populated by a real provider yet — UPD-047 ships a `StubPaymentProvider`. UPD-040 already provides Vault for secret storage. UPD-051 added the overage-authorization UX page. This feature wires Stripe into the rest of the platform and is the first time the platform charges actual money.

Functional requirements **FR-761 through FR-775** (section 125 of the FR catalog) are owned by this feature.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Free workspace upgrades to Pro with card (Priority: P1)

A Free-tier user is hitting the soft limits of the Free plan and decides to upgrade to Pro. From the workspace billing page they pick the Pro plan, enter a card in the embedded PCI-compliant card form, complete the EU 3D-Secure prompt if their bank requests it, and the workspace transitions to Pro instantly. Their first invoice arrives by email shortly after.

**Why this priority**: Without this flow the platform cannot collect any revenue, so it is the foundational P1 of the whole feature.

**Independent Test**: Run a Stripe-test-mode workspace through the upgrade flow end-to-end; assert that the local subscription row reaches `active` after the `customer.subscription.created` webhook, that quotas raise to Pro thresholds within 60 seconds, and that the first invoice has a Stripe-hosted PDF URL stored in the local invoices table.

**Acceptance Scenarios**:

1. **Given** a Free workspace with no Stripe customer record, **When** the owner completes the upgrade form with a successful test card, **Then** Stripe customer/payment-method/subscription objects are created with the workspace and tenant ids in metadata, the `customer.subscription.created` webhook lands, and the local subscription transitions to `active`.
2. **Given** a workspace whose card requires SCA, **When** the user submits the card form, **Then** the embedded card form orchestrates the 3D Secure challenge and the upgrade only completes after successful authentication.
3. **Given** a successful upgrade, **When** the next quota-check fires for the workspace, **Then** the new Pro caps apply without operator intervention.
4. **Given** a successful upgrade, **When** Stripe finalizes the first invoice, **Then** the local invoices table carries a row with `pdf_url`, `amount_total`, `amount_tax`, `period_start`, and `period_end` populated.
5. **Given** any of the above transitions, **When** the platform persists state, **Then** an audit chain entry is appended capturing the actor, before/after state, and the Stripe object ids.

---

### User Story 2 - Pro workspace hits quota and authorizes overage (Priority: P1)

A Pro workspace has consumed the included minutes mid-period. The next execution is paused, an in-app notification + email arrives titled "Authorize overage for this period," the owner clicks through, sees an estimated cost based on the current burn rate plus an optional cap, authorizes, and queued executions resume. Subsequent overage minutes show on the end-of-period invoice.

**Why this priority**: Overage UX is contractually required (FR-714 Option C — pause + notification + authorize button) and missing it makes Pro effectively unusable past the included quota, so it ranks alongside the upgrade flow as P1.

**Independent Test**: Drive a Pro workspace past its included minutes in Stripe test mode, assert that an execution receives the `OVERAGE_REQUIRED` decision and is paused, that an `overage.requested` notification surfaces with an authorize action, that a single click writes an `overage_authorizations` row and resumes paused executions, and that subsequent metered usage appears on the end-of-period invoice as a separate line item.

**Acceptance Scenarios**:

1. **Given** a Pro workspace at exactly 100% of included minutes, **When** the next execution runs the quota check, **Then** the execution transitions to `paused` with reason `overage_required` and a notification with an "Authorize overage" call-to-action is delivered to every workspace owner/admin.
2. **Given** a paused execution, **When** an authorized user opens the authorize page, **Then** the page surfaces the projected overage cost based on the last 7-day burn rate and offers an optional spend cap.
3. **Given** an authorize submission, **When** the platform persists the authorization, **Then** an `overage_authorizations` row exists for the active billing period, all paused executions for that workspace resume, and overage-period telemetry is emitted.
4. **Given** an authorized overage period, **When** the execution engine reports usage, **Then** Stripe usage records are submitted (live or batched within Stripe rate limits) and the end-of-period invoice contains a line item priced at the active `overage_price_per_minute`.
5. **Given** an active authorization, **When** the billing period ends, **Then** the authorization expires automatically and the next period's first overage triggers a fresh authorize prompt.

---

### User Story 3 - Failed payment grace and downgrade (Priority: P1)

A Pro workspace's card is declined on renewal. The platform records `past_due` immediately, sends three reminder emails over a 7-day grace period, lets Stripe Smart Retries continue to attempt the charge, and on day 7 — if no payment has succeeded — auto-downgrades the workspace to Free. Workspace data that exceeds Free quotas is flagged for cleanup but never silently destroyed.

**Why this priority**: Without this flow we either over-extend service to delinquent accounts or surprise paying users with hard cutoffs — both are unacceptable. The grace-with-cleanup behavior is the user-defined contract for this feature.

**Independent Test**: Trigger an `invoice.payment_failed` Stripe webhook in test mode, assert the local subscription transitions to `past_due`, fast-forward simulated wall-clock to day 7 without payment recovery, and verify the workspace is downgraded to Free, the workspace plan caps switch, the cleanup-flagged resources are tagged but not deleted, and an audit-chain entry is recorded for each transition.

**Acceptance Scenarios**:

1. **Given** an active Pro subscription, **When** Stripe sends `invoice.payment_failed`, **Then** the local subscription transitions to `past_due`, a `payment_failure_grace` row is created with `grace_ends_at` 7 days out, and the day-1 reminder email is sent.
2. **Given** an open `payment_failure_grace` row, **When** Stripe successfully retries the payment, **Then** the row is closed with resolution `payment_recovered`, the subscription returns to `active`, and reminders stop.
3. **Given** an open grace window, **When** day 3 and day 5 elapse without recovery, **Then** reminder emails 2 and 3 are sent (one per scheduled tick).
4. **Given** day 7 elapses without recovery, **When** the grace monitor runs, **Then** the subscription transitions to `suspended`, the workspace is downgraded to Free, resources exceeding Free caps are flagged for cleanup (extra workspaces archived, agents past the cap hidden until the user takes action), the subscription/grace pair is closed with resolution `downgraded_to_free`, and the user receives a "Downgraded to Free" notification.
5. **Given** a downgraded workspace, **When** the user adds a new card and reactivates, **Then** the subscription re-enters `active`, flagged resources are restored if still under cap, and an audit-chain entry covers the recovery.

---

### User Story 4 - Customer Portal self-service (Priority: P2)

A Pro user wants to update their card without going through the platform UI. They click "Manage billing," the platform creates a Stripe Customer Portal session, redirects them to the Stripe-hosted page, they update the card, and Stripe webhooks sync the new payment method back to the platform.

**Why this priority**: Self-service card maintenance reduces support load. P2 because Stripe Elements already exists for the upgrade path so users have at least one way to enter a card.

**Independent Test**: Trigger the portal session from a workspace with an active subscription, follow the redirect, update the test card via the Stripe-hosted UI, assert the `payment_method.attached` webhook lands and the local default payment-method row is updated.

**Acceptance Scenarios**:

1. **Given** a workspace with a Stripe customer record, **When** the owner clicks "Manage billing," **Then** the platform creates a portal session bound to that customer with a return URL back to the billing page.
2. **Given** a successful portal redirect, **When** the user updates the default card, **Then** Stripe emits `payment_method.attached` and the local default payment-method record reflects the new card brand/last4 within 60 seconds.
3. **Given** a portal session, **When** the user cancels their subscription via the portal, **Then** Stripe emits the corresponding event and the platform follows the cancellation-period-end flow as if the user had used the in-app cancel button.

---

### User Story 5 - Subscription cancellation period-end with reactivation (Priority: P2)

A Pro user clicks "Cancel subscription," provides an optional reason, and the platform schedules cancellation at period end. Pro features remain available until the period ends. The user can reactivate any time before the period flips, in which case the cancellation is reversed and no service interruption happens.

**Why this priority**: Critical for retention and aligns with Stripe's `cancel_at_period_end` semantics, but secondary to the upgrade and overage flows that gate revenue capture.

**Independent Test**: Submit cancellation, assert the local subscription transitions to `cancellation_pending` and Stripe carries `cancel_at_period_end=true`. Reactivate within the period and assert both sides return to `active`. Otherwise let the period end and assert the `customer.subscription.deleted` webhook flows the workspace down to Free.

**Acceptance Scenarios**:

1. **Given** an active Pro subscription, **When** the owner submits the cancellation with a reason, **Then** the platform sets the Stripe subscription to `cancel_at_period_end=true`, transitions the local status to `cancellation_pending`, persists the reason for retention analysis, and emails the user a confirmation with the period-end date.
2. **Given** a cancellation-pending subscription, **When** the user clicks "Reactivate" before period end, **Then** Stripe is set to `cancel_at_period_end=false` and the local status returns to `active`.
3. **Given** a cancellation-pending subscription, **When** the period ends without reactivation, **Then** the `customer.subscription.deleted` webhook flips the local status to `canceled`, the workspace transitions to Free, and the cleanup-flagging behavior from US3 applies.

---

### User Story 6 - Free workspace stores card without enabling overage (Priority: P2)

A Free user wants to put a card on file so a future upgrade is one click. They enter the card via Stripe Elements, the platform creates a Stripe customer record (or attaches to an existing one) and saves the payment method, but the Free plan's hard quota cap is preserved — overage stays disabled on Free even with a card on file.

**Why this priority**: Improves the upgrade conversion path but is not on the critical revenue path; P2.

**Independent Test**: Add a card while on Free, attempt to push the workspace past Free caps, assert the execution is blocked (not paused) and no Stripe charge is created. Then upgrade to Pro and assert the saved card pre-fills.

**Acceptance Scenarios**:

1. **Given** a Free workspace, **When** the owner adds a card, **Then** a Stripe customer is created (if absent) and the card is attached as the default payment method without spinning up a paid subscription.
2. **Given** a Free workspace with a card on file, **When** usage hits the Free cap, **Then** the next execution is blocked (not paused-with-authorize) and no Stripe charge is created, preserving the constitutional Free hard-cap rule.
3. **Given** a Free workspace with a card on file, **When** the owner upgrades to Pro, **Then** the saved card is pre-selected and the upgrade flow completes in one click.

---

### Edge Cases

- **Stripe API down or rate-limited**: outbound calls retry with exponential backoff up to a bounded ceiling, webhooks are queued for replay, and an admin-visible status indicator surfaces the degradation.
- **Webhook signature verification fails**: the request is rejected with 401, a security event is logged, and a pattern of failures triggers a super-admin alert.
- **Duplicate webhook events**: idempotency is enforced via a `processed_webhooks (provider, event_id)` primary key.
- **Webhook arrives before the local subscription row**: handler upserts (idempotent insert/update) so eventual consistency is acceptable; ordering is reconciled when both sides exist.
- **Currency**: prices are stored in EUR; Stripe handles per-locale display.
- **EU tax (IVA OSS)**: Stripe Tax computes the right rate per customer, populates `amount_tax`, and feeds the IVA OSS report.
- **Refunds**: out of self-service scope — super admin issues via the Stripe dashboard, then the standard webhooks reconcile state.
- **Chargeback**: `charge.dispute.created` triggers an automatic suspend on the affected subscription plus a super-admin alert.
- **Failed first payment on signup / trial conversion failure**: the subscription enters `past_due` immediately and the failed-payment grace flow takes over.
- **Webhook signing-secret rotation**: the verifier accepts both the previous and the new secret during the documented rotation window so no events are dropped.
- **Workspace deleted while a billing operation is in flight**: the in-flight operation completes, but webhook handlers detect the deleted workspace and route side effects (audit, notifications) without trying to update the gone resource.

## Requirements *(mandatory)*

### Functional Requirements

#### Provider abstraction

- **FR-761**: A `PaymentProvider` interface MUST expose `create_customer`, `attach_payment_method`, `create_subscription`, `update_subscription`, `cancel_subscription`, `report_usage`, `charge_overage`, `create_customer_portal_session`, `verify_webhook_signature`, and `handle_webhook_event` operations callable from the control-plane code paths used by Python and from the satellite Go services that participate in billing-relevant flows.
- **FR-762**: The platform MUST select the active provider implementation from configuration (`stripe`, `stub`) so the test/dev cluster can run against the stub without code changes.

#### Stripe concrete implementation

- **FR-763**: When the configured provider is Stripe, the platform MUST create Stripe customers with `tenant_id` and `workspace_id` in the customer metadata, attach payment methods, create fixed-price subscriptions for the active plan version, and create metered subscription items for overage when the active plan version defines an overage price.
- **FR-764**: The platform MUST embed a PCI-compliant card-entry form on the upgrade page, orchestrate Strong Customer Authentication / 3D Secure when the issuing bank requests it, and treat the upgrade as failed when SCA is not completed.
- **FR-765**: The platform MUST integrate Stripe Tax so that each invoice carries the correct EU IVA value in `amount_tax` and the IVA OSS aggregation includes platform-issued invoices.

#### Webhooks

- **FR-766**: The platform MUST expose a webhook endpoint at `/api/webhooks/stripe` that verifies HMAC signatures using the active and previously-active webhook signing secrets (rotation-safe), rejects unsigned/invalid payloads with 401, and emits a security event on rejection.
- **FR-767**: Webhook processing MUST be idempotent: each Stripe event id is recorded once in `processed_webhooks` and subsequent receipts return success without re-running side effects.
- **FR-768**: Handlers MUST exist for at minimum `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.trial_will_end`, `payment_method.attached`, and `charge.dispute.created`. Unknown event types MUST be acknowledged but not error.

#### Overage UX

- **FR-769**: When a quota check returns `OVERAGE_REQUIRED`, the platform MUST pause the execution, deliver an in-app and email notification to every workspace owner/admin with an "Authorize overage" action, persist the authorization on click, and resume any paused executions for that workspace immediately.
- **FR-770**: While an authorization is open, the platform MUST report metered overage to Stripe (live or batched within rate limits) so that the end-of-period invoice carries the overage line items at the active `overage_price_per_minute`. Authorizations MUST expire automatically at the billing period end.

#### Failed payment grace

- **FR-771**: On `invoice.payment_failed` the platform MUST transition the local subscription to `past_due`, open a `payment_failure_grace` row with `grace_ends_at` 7 days out, and let Stripe Smart Retries proceed.
- **FR-772**: The grace monitor MUST send reminder emails on day 1, day 3, and day 5 of the open window, close the row with `payment_recovered` if Stripe retries succeed, and on day 7 — if not recovered — suspend the subscription, downgrade the workspace to Free, flag resources that exceed Free caps for user-visible cleanup (do not delete), and append an audit-chain entry for each transition.

#### Self-service and lifecycle

- **FR-773**: The platform MUST be able to issue a Stripe Customer Portal session bound to the workspace's customer record with a return URL pointing back to the billing page, and MUST sync state changes performed in the portal back via webhooks.
- **FR-774**: The platform MUST persist Stripe-issued invoices locally with the Stripe-hosted PDF URL, period range, totals, tax, and status, and the workspace billing page MUST list the most recent invoices with downloadable PDFs.
- **FR-775**: The cancellation flow MUST set `cancel_at_period_end=true`, mark the local subscription `cancellation_pending`, retain Pro features until period end, allow reactivation before period end, and on period end (via `customer.subscription.deleted`) downgrade to Free and apply the same cleanup behavior as the failed-payment grace path.

#### Cross-cutting

- **FR-A1**: A Free workspace MUST be able to add a card on file without enabling overage; Free's hard-cap rule (constitutional rule 25) takes precedence over a card being on file.
- **FR-A2**: An audit-chain entry MUST be appended on every billing-relevant state transition (subscription status change, payment method change, invoice issued, dispute opened, grace entered/closed, downgrade, reactivation).
- **FR-A3**: All Stripe secrets (API key, webhook signing secret) MUST be loaded from Vault at the canonical paths and never logged.
- **FR-A4**: Dev/test clusters MUST run against Stripe test mode; production runs against Stripe live mode. Mode is decided by configuration, not code.

### Key Entities

- **PaymentMethod** — a Stripe payment-method record copied locally for fast lookup; tenant-scoped (workspace-scoped where applicable). Carries the brand/last4/expiry plus the Stripe id.
- **Invoice** — a tenant-scoped local mirror of a Stripe invoice with the totals, tax breakdown, status, period range, and PDF URL. Used by the invoices page and audit pulls.
- **ProcessedWebhook** — primary key `(provider, event_id)` used to enforce webhook idempotency.
- **PaymentFailureGrace** — open record while a subscription is in the failed-payment grace window; tracks reminders, ends-at, and resolution.
- **OverageAuthorization** — already exists in UPD-047; this feature drives the lifecycle (open via the authorize action, close at period end, link to Stripe usage records).
- **Subscription / Plan / PlanVersion** — already exist in UPD-047; this feature populates the `stripe_*` columns from real Stripe state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A Free user completes an upgrade-to-Pro flow (including SCA) in under 3 minutes on a typical broadband connection.
- **SC-002**: After a successful upgrade, the workspace's quotas reflect the new plan within 60 seconds of the `customer.subscription.created` webhook.
- **SC-003**: Webhook processing achieves p95 end-to-end latency (signature verify → handler complete → idempotency row written) under 5 seconds at 50 events/min.
- **SC-004**: 100% of duplicate webhook deliveries (replays from Stripe within a 14-day window) are detected via the idempotency table and produce no extra side effects.
- **SC-005**: When `invoice.payment_failed` fires, the workspace receives reminder emails on day 1, day 3, and day 5 (±2 hours), and the day-7 downgrade triggers within 1 hour of the grace window expiring.
- **SC-006**: 100% of overage authorizations result in paused executions resuming within 30 seconds; the next billing-period invoice contains line items priced at the active `overage_price_per_minute`.
- **SC-007**: Free workspaces with a card on file never produce a Stripe charge until the workspace is upgraded to a paid plan.
- **SC-008**: Cancellations preserve Pro features for the full remaining billing period (zero unintended interruptions during the period) and reactivation before period end keeps the same Stripe subscription record (no churn artifacts).
- **SC-009**: 100% of EU invoices carry a non-null `amount_tax` calculated by Stripe Tax and feed into the IVA OSS report.
- **SC-010**: Every billing-relevant state transition emits exactly one audit-chain entry, verifiable via `tools/verify_audit_chain.py` after a journey run.

## Assumptions

- The active and previous webhook signing secrets are stored in Vault and rotated through a documented playbook with overlap.
- The default workspace billing currency is EUR; multi-currency support is out of scope for this feature.
- Refunds, partial credits, and proration overrides remain super-admin-only via the Stripe dashboard; the platform reconciles them via standard webhooks.
- Stripe handles the SCA/3D-Secure flow inside the embedded card form; the platform is not authorized to bypass.
- The grace monitor cron runs at least daily in dev/staging/prod so the day-1/3/5/7 reminders fire close to schedule.
- Notifications (in-app + email) are dispatched via the existing UPD-077 notification stack added in the data-lifecycle line of work.
- The Free hard-cap rule (constitution rule 25) is enforced by the existing quota engine; this feature only ensures it is *not* relaxed when a Free workspace adds a card.
- Dev cluster always runs Stripe test mode; this feature does not introduce a "no provider" mode beyond the existing stub.
