# Feature Specification: UPD-054 — SaaS E2E Journey Tests

**Feature Branch**: `107-saas-e2e-journeys`
**Created**: 2026-05-05
**Status**: Draft
**Input**: User description: "UPD-054 — 16 new SaaS-specific E2E journey tests (J22–J37) covering tenant lifecycle, plans/subscriptions/quotas, marketplace, abuse prevention, billing, Hetzner topology, cross-tenant isolation, default-tenant immutability, and free-tier cost protection. Extends the existing UPD-038 E2E framework (J01–J21) so the full SaaS pass green-lights when all 37 journeys pass on the dev cluster."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Tenant lifecycle and isolation are validated end-to-end (Priority: P1)

The platform team needs unattended, reproducible evidence that the SaaS tenant model is sound: every Enterprise tenant can be provisioned to a healthy state, isolation between tenants holds across every public surface, the default tenant is structurally immutable, the underlying Hetzner cluster is reachable at the documented hostnames with valid TLS, and a tenant can be torn down to completion without leaking data or DNS records. Without this evidence the SaaS pass cannot ship: a single regression in tenant boundaries is a customer-data incident.

**Why this priority**: Tenant correctness is the foundation that every other SaaS capability stands on. A billing bug is recoverable; a cross-tenant leak is not. This slice MUST land first because the platform cannot be safely opened to outside customers if tenants are not provably isolated.

**Independent Test**: Operators run `make e2e-saas-suite` against a dev kind cluster after a fresh Helm deploy. The six journeys in this slice (J22, J24, J27, J29, J31, J36) execute in parallel and emit a single junit report. The slice passes if the report shows zero failures across all six AND the cleanup hook leaves no orphan Hetzner DNS records, no orphan database rows, and no orphan TLS Secret resources. This slice is releasable on its own as evidence that the tenant subsystem is production-ready, even before billing or marketplace surfaces are exercised.

**Acceptance Scenarios**:

1. **Given** a fresh dev cluster post-Helm-install, **When** the J22 journey provisions a new Enterprise tenant via `/admin/tenants/new`, **Then** within 5 minutes the tenant row is committed, the six DNS records (apex/api/grafana x {A, AAAA}) are reachable from a public resolver, the wildcard TLS cert validates against `<slug>.musematic.ai`, the first-admin invite email is observed in the test mailbox, the audit chain entry `tenants.created` is recorded, AND the first admin can complete password + MFA setup and reach the tenant admin dashboard.
2. **Given** a provisioned tenant `acme` and a user `userA@default.musematic.ai`, **When** J31 attempts to read `acme`'s workspaces, agents, executions, audit entries, costs, and secrets via crafted REST + WebSocket calls, **Then** every cross-tenant access returns HTTP 404 (NOT 403, to avoid existence leakage), no row data appears in any response body, AND the same calls succeed when invoked under a privileged platform-staff role (proving RLS isn't accidentally blocking legitimate access).
3. **Given** the platform default tenant in healthy state, **When** J36 attempts to delete, suspend, or rename it via API, AND attempts a database migration that would drop the constraint enforcing its existence, **Then** every API call returns HTTP 403 with the documented `default_tenant_immutable` error code, the migration aborts at the constraint check, AND a fresh `kubectl get tenant default -o jsonpath='{.status.phase}'` still reports `Active`.
4. **Given** an Enterprise tenant `acme` past its 30-day cancellation grace, **When** J27 advances `acme` to phase 2 of the data-lifecycle cascade, **Then** all `acme`-scoped database rows are purged, the six DNS records are removed (idempotent — re-run produces no orphans), the wildcard cert remains intact (per FR-787), an audit-chain tombstone entry is appended and verified by `tools/verify_audit_chain.py`, AND a re-provision attempt under the same slug succeeds without conflict.

---

### User Story 2 — Billing and subscription flows are validated end-to-end (Priority: P2)

Finance and Customer Success need confidence that the Stripe-backed billing pipeline behaves correctly across every state transition: Free → Pro upgrades, trial conversion, payment failure → grace → recovery OR auto-downgrade, cancellation with reactivation window, and webhook idempotency under replay attack. Bugs here cause direct revenue loss or customer-facing churn.

**Why this priority**: Billing is the second-most-critical SaaS surface after tenant correctness. The first paying customer cannot onboard until this slice green-lights. This is P2 (not P1) only because tenants can be provisioned correctly without billing — but no tenant can pay without it.

**Independent Test**: Operators run `make e2e-saas-suite -- --suite billing` against a dev cluster wired to Stripe **test mode**. The four journeys in this slice (J28, J32, J33, J34) execute against a fixture that issues Stripe test cards (`4242 4242 4242 4242`, `4000 0000 0000 0341` for failures, `4000 0027 6000 3184` for 3DS), replays webhook events via `stripe-cli`, and uses Stripe's clock-advance API to simulate trial expiry. The slice passes if all four journeys green-light, the Stripe Customer Portal shows the expected invoice + subscription state, AND no real charges are issued (verified by zero entries in `payment_intents` keyed to non-test cards).

**Acceptance Scenarios**:

1. **Given** a Free workspace owner, **When** J28 initiates Free → Pro upgrade with test card `4242…`, **Then** the first invoice settles, status flips to `active`, the workspace immediately gains Pro quotas, AND a subsequent transaction on a `4000 0000 0000 0341` (decline) test card surfaces an `action_required` UX prompt without breaking the subscription.
2. **Given** an active Pro subscription with a payment-failed event, **When** J28 simulates 7 days of grace via Stripe clock-advance, **Then** daily reminder notifications are emitted, the subscription transitions to `past_due`, recovery via card replacement on day 5 restores `active`, AND a second run that exhausts the grace period auto-downgrades to Free with a clear "downgraded" notification and zero data loss.
3. **Given** a duplicate Stripe webhook event (replayed via `stripe-cli`), **When** J32 sends the second copy, **Then** the API returns HTTP 200 with an idempotency-key match in the response, no duplicate state mutation occurs (subscription period is not double-extended, the audit chain shows exactly one `billing.invoice_paid` entry), AND the dedupe TTL covers the documented Stripe replay window (>= 7 days).
4. **Given** a Pro user mid-cycle, **When** J34 cancels and the subscription enters `cancellation_pending`, **Then** Pro features remain available until period-end, a reactivation click before period-end restores `active` with no proration surprise, AND a separate run that lets the period elapse cleanly transitions to `canceled` with downgrade-to-Free taking effect at the next quota check.

---

### User Story 3 — Plans, quotas, and cost-protection guarantees are validated (Priority: P2)

Engineering needs to prove that quota enforcement is air-tight (Free users cannot incur paid-tier cost), plan versioning is non-destructive (existing subscriptions don't get silently re-priced), and overage handling matches the documented contract (paused state for Pro, hard cap for Free, never for Enterprise).

**Why this priority**: This slice catches the class of bug that destroys customer trust the fastest — a Free user receiving a surprise invoice, or a Pro user discovering a price hike retroactively. Same priority as billing because the two slices share the Stripe + plans surface; logically distinct because this slice exercises *limits and pricing rules* rather than payment plumbing.

**Independent Test**: `make e2e-saas-suite -- --suite plans_subscriptions` runs J23, J30, and J37 in parallel. The slice passes if (a) Free workspaces hit hard cap with HTTP 402 and zero overage cost incurred (verified against ClickHouse cost-per-execution audit table), (b) Pro overage produces a paused state and resumes after the user authorizes, (c) a published plan version edit is rejected and a new-version path is the only mutation route, AND (d) existing subscriptions on version N continue billing at version N's price after a publish to version N+1.

**Acceptance Scenarios**:

1. **Given** a Free workspace at 95% of monthly quota, **When** J23 attempts to run executions until exhaustion, **Then** the next call returns HTTP 402 with body `{"code":"quota_exceeded",...}`, the UI displays the documented "Upgrade to Pro" CTA, the cost-events audit row records zero charge for the rejected attempt, AND counters reset cleanly at the next period boundary.
2. **Given** an active subscription on Pro plan version 1 (49 EUR), **When** J30 has the super-admin publish a new version 2 (59 EUR), **Then** the existing subscription continues at 49 EUR until opt-in, new signups land on 59 EUR, an attempt to edit the already-published version 1 returns HTTP 409 with `version_immutable`, AND opt-in upgrade emits a prorated invoice line that reconciles to the documented prorated formula within +/-1 cent.
3. **Given** a Free user, **When** J37 attempts to invoke a premium model, request a context window above the Free tier cap, OR run repeatedly until the hard cap, **Then** each attempt is rejected with `quota_exceeded` BEFORE any external model call is dispatched (verified by zero outbound model-router invocations in the trace), AND the period total cost is exactly 0 cents.

---

### User Story 4 — Marketplace, abuse prevention, and wildcard TLS renewal are validated (Priority: P3)

Beyond the core tenant + billing model, the SaaS pass introduces several support surfaces — multi-scope marketplace publishing, signup abuse defenses, and automated wildcard cert renewal — that each need standalone end-to-end coverage. These are P3 because the platform can ship to early customers without them being battle-tested (a marketplace bug doesn't break paying customers, abuse rules can be hardened post-launch, cert renewal is 30 days out from any first deploy), but they are still gating the *pass* exit criteria.

**Why this priority**: Each journey in this slice covers a real but secondary user concern. Skipping them would not block first revenue; skipping them indefinitely would let regressions accumulate.

**Independent Test**: `make e2e-saas-suite -- --suite supporting` runs J25, J26, J35 in parallel against a dev cluster with fixtures that (a) provide two Enterprise tenants `acme` and `globex` with the public-marketplace consume flag set differently, (b) inject crafted bot-signup traffic, and (c) artificially advance the cert clock via cert-manager's testing endpoint. The slice passes if marketplace visibility matches the documented scope-and-flag matrix exactly, abuse signals all trigger their documented defenses (with zero false positives on the legitimate user fixtures), and the cert renewal completes without interrupting in-flight HTTPS requests.

**Acceptance Scenarios**:

1. **Given** a default-tenant user `creator@default.musematic.ai`, **When** J25 publishes an agent to the `public_default_tenant` scope and the super-admin approves it, **Then** a second default-tenant user discovers and runs it; Enterprise tenant `acme` (with `consume_public_marketplace=true`) sees and runs it read-only; Enterprise tenant `globex` (without the flag) does NOT see it; AND a tenant-scope agent inside `acme` is NEVER visible from `globex` regardless of either flag.
2. **Given** a fresh signup IP, **When** J26 issues 10 signup attempts in quick succession, **Then** the velocity rule blocks the 10th attempt with `signup_velocity_exceeded`; a disposable-email signup is rejected pre-creation; a previously-suspended account is barred from login until super-admin lifts the suspension; AND a Free user attempting a premium-model + long-execution combination is rejected before any model invocation (cost-protection cross-check with J37).
3. **Given** a wildcard cert with `notAfter` set 25 days into the future, **When** J35 advances the cert-manager renewal trigger, **Then** cert-manager initiates renewal, the renewed cert is written to the same Secret name, ingress-nginx hot-reloads without dropping in-flight requests (verified by 100% success of a parallel HTTPS load-tester against `app.dev.musematic.ai`), AND a forced renewal failure variant fires the `WildcardCertRenewalFailing` Prometheus alert within 15 minutes.

---

### Edge Cases

- **Stripe test-mode webhooks**: webhook signing secret rotation mid-test must not poison the test (the fixture re-fetches the secret per-test).
- **Hetzner DNS rate limiting**: parallel J22 + J27 runs MUST serialize per-zone calls to stay under the 1 req/s burst limit; otherwise tests become flaky against the real Hetzner test zone.
- **Default-tenant slug collision**: a malicious actor attempting to provision an Enterprise tenant with slug `default` MUST be rejected with `slug_reserved` BEFORE any DNS or DB write fires.
- **Trial expiry race**: a card decline on the exact day a trial expires must not leave the subscription in a hybrid state — J33 explicitly tests this race.
- **Cancellation reactivation race**: a reactivation click sent at second 59 of period-end must either succeed cleanly (period extended) OR fail cleanly (downgrade-to-Free already fired); J34 verifies a window guard prevents the half-state.
- **Duplicate cleanup**: cleanup hooks MUST be idempotent — re-running the same fixture teardown after a partial failure (e.g., DNS removed, DB cleanup interrupted) must complete without raising.
- **Audit-chain integrity under parallel runs**: many journeys append audit entries concurrently; the suite MUST verify chain integrity at the end of the run, not per-test (chain verification is whole-tail-or-nothing).
- **Long-tail journey timeout**: any journey that exceeds 8 minutes of wall-clock time MUST be hard-killed and reported as a failure with a fixture-state dump (avoids "stuck-forever" CI runs).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-792 (J22 — Tenant Provisioning)**: System MUST provide an automated end-to-end journey that provisions a new Enterprise tenant from the admin UI, asserts DNS + TLS + audit-chain + invite-email side-effects, and walks the first admin through password + MFA setup to a healthy admin dashboard, all within a single test run.
- **FR-793 (J23 — Quota Enforcement)**: System MUST provide an automated journey that exercises Free hard-cap (HTTP 402), Pro overage paused-then-resumed, Enterprise unlimited, and the period-boundary counter reset path.
- **FR-794 (J24 — Enterprise Tenant Provisioning Variants)**: System MUST provide an automated journey that covers super-admin-driven Enterprise tenant creation with branding, SSO config, and per-tenant feature flag editing.
- **FR-795 (J25 — Marketplace Multi-Scope)**: System MUST provide an automated journey that validates the workspace / tenant / public_default_tenant scope visibility matrix end-to-end including the `consume_public_marketplace` flag's effect on Enterprise tenants.
- **FR-796 (J26 — Abuse Prevention)**: System MUST provide an automated journey that validates signup velocity, disposable-email rejection, suspension/un-suspension, and Free-tier cost-protection rejection paths.
- **FR-797 (J27 — Tenant Lifecycle Cancellation)**: System MUST provide an automated journey covering cancellation initiation, data export download, 30-day grace simulation, phase-2 cascade (data + DNS + TLS), and audit-tombstone retention.
- **FR-798 (J28 — Billing Lifecycle)**: System MUST provide an automated journey covering Free → Pro upgrade, first payment, overage threshold + authorize, payment failure → grace → recovery, payment failure → grace exhausted → auto-downgrade, cancellation, and reactivation.
- **FR-799 (J29 — Hetzner Topology)**: System MUST provide an automated journey that asserts platform Helm install, the apex/app/api/grafana DNS records, the wildcard + apex TLS certs, and per-tenant DNS create/delete via the dns_automation client.
- **FR-800 (J30 — Plan Versioning)**: System MUST provide an automated journey that exercises plan version 2 publication, the immutability of version 1 for existing subscribers, the rejection of edits to a published version, and prorated opt-in upgrade.
- **FR-801 (J31 — Cross-Tenant Isolation)**: System MUST provide an automated journey that runs negative-test API calls across every tenant-scoped resource (workspaces, agents, executions, audit, costs, secrets) AND a positive-test under privileged platform-staff role.
- **FR-802 (J32 — Stripe Webhook Idempotency)**: System MUST provide an automated journey that replays a Stripe webhook and asserts no double-state-mutation, response 200 idempotent, and audit-chain single-entry semantics.
- **FR-803 (J33 — Trial-to-Paid Conversion)**: System MUST provide an automated journey covering trial signup, the day-11 reminder, the day-14 charge, AND the card-failure variant transitioning to `past_due`.
- **FR-804 (J34 — Subscription Cancellation and Reactivation)**: System MUST provide an automated journey covering cancellation, the `cancellation_pending` window, reactivation, and the period-end-without-reactivation path.
- **FR-805 (J35 — Wildcard TLS Renewal)**: System MUST provide an automated journey that simulates near-expiry and asserts cert-manager renewal completes without service interruption AND that a forced renewal failure fires the alert.
- **FR-806 (J36 — Default Tenant Constraint)**: System MUST provide an automated journey that exercises every forbidden operation against the default tenant (delete via API, suspend, rename, migration that drops the existence constraint) and confirms the default tenant remains in healthy state.
- **FR-807 (J37 — Free Plan Cost Protection)**: System MUST provide an automated journey that validates the three Free-tier rejection paths (premium model, oversize context, hard-cap on small executions) AND verifies zero overage cost is incurred.
- **FR-808 (Test Infrastructure)**: System MUST provide a parallel-execution-capable test suite (<= 30-minute wall-clock for the full SaaS pass), a Stripe-test-mode integration (test cards + webhook replay), a DNS-automation harness (mock or real Hetzner test zone), a wildcard-TLS-renewal harness, J01–J21 regression preservation, a CI promotion gate that blocks merge to `main` on any failure, failure-artifact capture (screenshots + network traces + audit-chain dumps), and a documented runbook covering fixture lifecycle and debugging.

### Key Entities *(include if feature involves data)*

- **Journey**: A single end-to-end test scenario identified by a `J##` label. Each journey owns a primary user actor, a sequence of user-facing steps, a set of side-effects to observe, and a set of cleanup obligations. Journeys are organised into suites by domain.
- **Suite**: A grouping of journeys that share fixtures and can be run as a unit (e.g., `billing` suite covers J28, J32, J33, J34). Suites are the unit of `make e2e-saas-suite -- --suite <name>` invocation.
- **Fixture**: A reusable setup/teardown helper (tenants, users, Stripe test mode, DNS) consumed by multiple journeys. Fixtures own resource lifecycle and MUST be idempotent on teardown.
- **Test report**: The artefact set produced by a journey on completion (JUnit XML, optionally screenshots, network HAR traces, audit-chain dumps). Used by the CI promotion gate and by operators triaging a failure.
- **Promotion gate**: The CI job that runs the full SaaS pass against a dev cluster and blocks merge to `main` if any journey reports a failure. It is the single point at which the SaaS pass exit criteria are enforced.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 16 new journeys (J22–J37) green-light against a freshly deployed dev cluster, with zero flaky failures over 5 consecutive runs.
- **SC-002**: The full SaaS suite (J22–J37) completes in <= 30 minutes wall-clock (p95) when run in parallel on the documented runner spec.
- **SC-003**: J01–J21 (UPD-038 baseline) regression suite continues to pass alongside the new journeys, with zero new failures attributable to UPD-054.
- **SC-004**: The CI promotion gate blocks merge to `main` on any single journey failure (verified by deliberately breaking one journey in a draft PR and observing the gate trip).
- **SC-005**: When a journey fails, the operator receives a single linked artefact bundle containing screenshots, the network HAR for the failing step, the audit-chain entries for the test run, and the cleanup-state dump — sufficient to diagnose 90% of failures without rerunning the test.
- **SC-006**: Cleanup hooks leave zero orphan resources after a 100-journey run: zero orphan Hetzner DNS records, zero orphan database rows in tenant-scoped tables, zero orphan Stripe Customers in test mode, and zero orphan Kubernetes Secrets bearing test-tenant labels.
- **SC-007**: The Stripe-test-mode harness incurs zero real-money charges across the full SaaS suite (verified by Stripe dashboard showing only test-mode `payment_intents`).
- **SC-008**: The end-to-end journey count grows from 21 (UPD-038) to 37 (UPD-054), and the documented exit criteria for the SaaS pass references all 37 journeys explicitly.
- **SC-009**: The documented runbook for E2E maintenance covers fixture lifecycle, common debugging steps, the parallel-runner architecture, and the failure-artefact format such that an operator new to the codebase can triage their first journey failure within 30 minutes of reading.

## Assumptions

- The UPD-038 E2E framework (Playwright + custom Python orchestration, kind-cluster fixtures, parallel runner, cleanup hooks) is in place and is extended in this feature rather than rewritten. New journeys follow the same conventions for actor management, fixture lifecycle, and report emission.
- A Stripe **test-mode** account is reachable from the CI runner with credentials provisioned through the existing Vault path family (`secret/data/musematic/dev/billing/stripe/...`). No production Stripe credentials are ever read by this suite.
- A Hetzner DNS test zone (separate from production `musematic.ai`) is available for the J29 / J22 / J27 journeys. Where a real Hetzner zone is unavailable, a documented mock provider is substituted with reduced coverage and a clear `requires_live_dns` skip-marker. Operators can opt into live-DNS coverage via `RUN_J29=1`.
- The dev cluster used for the promotion gate is the same `musematic-dev` cluster delivered by UPD-053 (Hetzner production+dev clusters). The test suite assumes its presence and addresses; bringing up an alternative cluster is out of scope.
- The audit-chain integrity tool (`tools/verify_audit_chain.py`) is invoked once per suite run rather than per-journey, since the chain is a single global ledger.
- Test data uses synthetic identities only — no real customer data, no real payment cards. Synthetic-identity generation is owned by the existing `tests/e2e/fixtures/users.py` helper.
- The 30-minute wall-clock target for SC-002 assumes >= 4 parallel test workers on a runner with >= 8 vCPU / 16 GiB RAM. Single-worker invocations are documented as roughly 2 hours and are intended for local debugging only.
- The CI promotion gate is the enforcement mechanism for the SaaS pass exit criteria; operators are not expected to run J01–J37 by hand on every PR. Local invocation is for the journey owner working on the journey, plus periodic full-suite smoke runs by the platform team.
- Failure artefacts (screenshots + HAR + audit dump) are uploaded to the existing CI artefact bucket (the same one UPD-038 uses); no new storage system is introduced.
- Free-tier cost protection (J37) and abuse prevention (J26) take their thresholds and rejection criteria from the constitution / governance configuration committed elsewhere; this feature exercises them but does not redefine them.
- The promotion gate runs *after* the helm-lint snapshot diff, the unit test gates, and the existing UPD-038 e2e job — they are sequenced so that a fast lint failure blocks early and the long-running e2e gate runs only when cheaper checks have passed.
