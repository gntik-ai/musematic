---

description: "Task list for UPD-054 — SaaS E2E Journey Tests"
---

# Tasks: UPD-054 — SaaS E2E Journey Tests (J22–J37)

**Input**: Design documents from `/specs/107-saas-e2e-journeys/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: This feature **is** the test suite — every task adds test code, fixture code, or test infrastructure. Acceptance is gated by SC-001..SC-009 from spec.md, not by line coverage.

**Organization**: Tasks are grouped by user story (US1–US4 from spec.md). Six journey scaffolds (J27 / J28 / J29 / J32 / J33 / J34 / J35) already exist as skip-marked stubs left by UPD-052 / UPD-053; their tasks fill in the body and remove the skip marker.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US4); setup/foundational/polish tasks omit it
- Each task lists the exact file path

## Path Conventions

- E2E suite root: `tests/e2e/`
- Fixtures: `tests/e2e/fixtures/`
- Journeys: `tests/e2e/journeys/`
- CI: `.github/workflows/ci.yml`
- Docs/runbooks: `docs/operations/...`
- Makefile targets: repo-root `Makefile`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install dev/CI prerequisites, scaffold the suite plumbing the four fixtures and sixteen journeys depend on. Nothing here exercises a journey body.

- [X] T001 [P] Add `stripe-cli` install step to the existing `journey-tests` job in `.github/workflows/ci.yml` (immediately after the `Setup Helm` step). Pin to `stripe-cli` v1.21+; verify checksum from the GitHub release. Documents matching local-install path in `quickstart.md` § Prerequisites.
- [X] T002 [P] Add two convenience targets `e2e-saas-suite` and `e2e-saas-acceptance` to the root `Makefile` per `quickstart.md` § 3 / § 5. The first runs J22–J37; the second runs J01–J37 back-to-back. Both honour `E2E_JOURNEY_WORKERS` (default 4) and `RUN_J29` env vars.
- [X] T003 [P] Add a `e2e-saas-soak` target to the root `Makefile` per `quickstart.md` § 7 — runs `e2e-saas-suite` 100x in a tight loop and exits non-zero if any iteration fails. Documents the SC-006 verification path.
- [X] T004 [P] Add a `tests/e2e/scripts/verify_no_orphans.py` helper that calls `list_test_tenants()`, `list_test_stripe_customers()`, and `list_test_dns_records()` (all from the new fixtures, see Phase 2) and exits non-zero if any list is non-empty. Used by the soak workflow and the quickstart's tear-down step.
- [X] T005 [P] Document fixture lifecycle and parallel-runner architecture in the existing `tests/e2e/README.md` under a new "## SaaS pass — J22–J37" section that cross-links to the new `docs/operations/e2e-suite-maintenance.md` runbook (created in Phase 7).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The four new fixture modules under `tests/e2e/fixtures/` and the CI matrix entry every journey depends on. Until this phase is complete no journey body can be written.

⚠️ CRITICAL: no user-story work begins until Phase 2 is complete.

- [X] T006 [P] Create `tests/e2e/fixtures/tenants.py` per `contracts/tenants-fixture.md`. Implements `provision_enterprise()` async-CM, `list_test_tenants()` orphan helper, the `TestTenant` dataclass, and the `e2e-` slug-prefix safety guard. Drives the public `POST /api/v1/admin/tenants` endpoint (UPD-053); polls audit chain for `tenants.created` before yielding.
- [X] T007 [P] Create `tests/e2e/fixtures/users.py` per `data-model.md` § "in-process test-fixture data structures". Implements `synthetic_user(tenant, role, mfa_enrolled)`, the `TestUser` dataclass, and the `.invalid`-TLD email aliasing rule. Wraps the existing TOTP test helpers from UPD-014 for the MFA enrollment path.
- [X] T008 [P] Create `tests/e2e/fixtures/stripe.py` per `contracts/stripe-fixture.md`. Implements `StripeTestModeClient` with the `LiveKeyDetectedError` guard at `__init__`, the four customer/subscription helpers, the `advance_test_clock` helper, the `trigger_webhook`/`resend_webhook` pair, and `purge_test_customers()`. Reads credentials via the existing `SecretProvider` (constitution rule 11).
- [X] T009 [P] Create `tests/e2e/fixtures/dns.py` per `contracts/dns-fixture.md`. Implements `MockDnsProvider`, `LiveHetznerDnsProvider`, the `DnsTestProvider` Protocol, and the `build_dns_test_provider(settings)` factory. Includes the `ProductionZoneRefusedError` guard and the per-zone `pytest-xdist` filelock.
- [X] T010 Wire all four new fixtures into `tests/e2e/conftest.py` via the existing `pytest_plugins` registration mechanism (mirrors how `fixtures.workspace`, `fixtures.agent`, etc. are registered). New entries: `fixtures.tenants`, `fixtures.users`, `fixtures.stripe`, `fixtures.dns`.
- [X] T011 [P] Extend the existing `tests/e2e/journeys/test_helpers_contract.py` smoke test (UPD-038) to enforce the new `journey-template.md` rules — specifically, every `test_j*.py` file MUST have a module-level `pytestmark` list containing `pytest.mark.journey`, the matching `pytest.mark.j{NN}`, and `pytest.mark.timeout(480)`. The contract test fails the suite if any new journey file misses these markers.
- [X] T012 Add the new SaaS-pass matrix entry to `.github/workflows/ci.yml`'s `journey-tests` job per `contracts/promotion-gate.md` § "Step layout". Required-status name `journey-tests (saas-pass)`. Runs `tests/e2e/journeys/test_j2[2-9]*.py tests/e2e/journeys/test_j3[0-7]*.py -m journey -n 4 --timeout=480`. Includes the audit-chain verifier step (`if: matrix.suite == 'saas-pass' && always()`).
- [X] T013 [P] Update the `paths-filter` block in `.github/workflows/ci.yml:73` to add the SaaS-pass trigger paths from `contracts/promotion-gate.md` § "Trigger conditions" (tenants/, accounts/, billing/, marketplace/, abuse_prevention/, data_lifecycle/, governance/, admin UI route group, Helm, e2e tests).

**Checkpoint**: fixtures and CI plumbing ready. Journey work for any user story can now begin in parallel.

---

## Phase 3: User Story 1 — Tenant lifecycle and isolation (Priority: P1) 🎯 MVP

**Goal**: A platform engineer running `make e2e-saas-suite -- --suite tenant_architecture` against a freshly deployed dev cluster sees green-light evidence that Enterprise tenants can be provisioned, isolated, lifecycle-managed, AND that the default tenant is structurally immutable. The cleanup hook leaves zero orphan resources.

**Independent Test**: `pytest tests/e2e/journeys/test_j22_*.py tests/e2e/journeys/test_j24_*.py tests/e2e/journeys/test_j27_*.py tests/e2e/journeys/test_j29_*.py tests/e2e/journeys/test_j31_*.py tests/e2e/journeys/test_j36_*.py -m journey -n 4` — the six journeys complete in ≤ 15 minutes wall-clock with zero failures and zero orphan tenants/DNS records detected by `verify_no_orphans.py`.

### Implementation for User Story 1

- [X] T014 [P] [US1] Create `tests/e2e/journeys/test_j22_tenant_provisioning.py` per `contracts/journey-template.md` and spec.md US1 acceptance scenario 1. Drives super-admin `/admin/tenants/new`; asserts tenant row, 6-record DNS observed, TLS cert, first-admin invite delivered, audit chain entry; walks first admin through password + MFA setup + reaching admin dashboard. Uses fixtures `tenants.provision_enterprise`, `users.synthetic_user`, `dns.build_dns_test_provider`.
- [X] T015 [P] [US1] Create `tests/e2e/journeys/test_j24_enterprise_provisioning.py` covering super-admin-driven Enterprise tenant creation with branding upload, SSO config, and per-tenant feature-flag editing (FR-794). Uses `tenants.provision_enterprise(plan="enterprise")` plus the existing `http_client` fixture for direct admin API calls.
- [X] T016 [US1] Replace the skip-marked stub in `tests/e2e/journeys/test_j27_tenant_lifecycle_cancellation.py` (created by UPD-052) with the full body per spec.md US1 acceptance scenario 4. Drives cancellation initiation, tenant data export download (asserts MinIO bucket `tenant-data-exports`), 30-day grace simulation, phase-2 cascade (data + DNS + TLS verified absent), audit-chain tombstone retention, AND a re-provision under the same slug to verify idempotent cleanup. Removes the existing `pytest.mark.skipif(...RUN_J27...)` guard.
- [X] T017 [US1] Replace the skip-marked stub in `tests/e2e/journeys/test_j29_hetzner_topology.py` (created by UPD-053) with the full body per FR-799. Asserts Helm install state on the kind cluster, the apex/app/api/grafana DNS records, the wildcard + apex TLS certs, and the per-tenant DNS create/delete cycle via the `dns_automation` runtime. Keeps the `RUN_J29=1` opt-in for live-Hetzner mode but defaults to mock.
- [X] T018 [P] [US1] Create `tests/e2e/journeys/test_j31_cross_tenant_isolation.py` per spec.md US1 acceptance scenario 2. Provisions two tenants via the fixture; runs negative-test API calls across every tenant-scoped resource (workspaces, agents, executions, audit, costs, secrets) AND a positive-test under the platform-staff role. Asserts 404 (NOT 403) on every cross-tenant attempt to prevent existence leakage.
- [X] T019 [P] [US1] Create `tests/e2e/journeys/test_j36_default_tenant_constraint.py` per spec.md US1 acceptance scenario 3 and FR-806. Attempts each forbidden default-tenant op (delete via `/admin/tenants/default` API → 403; suspend → blocked; rename → blocked); attempts a migration that drops the existence constraint via the existing test-DB migration helper and asserts the migration aborts; final-state assertion that the default tenant is still `Active`.

**Checkpoint**: all 6 US1 journeys pass; the SaaS pass minimum gate (tenant correctness) is releasable on its own.

---

## Phase 4: User Story 2 — Billing and subscription flows (Priority: P2)

**Goal**: A finance/CS engineer running `make e2e-saas-suite -- --suite billing` confirms the Stripe-backed billing pipeline behaves correctly across upgrade, trial-to-paid, payment-failure-recovery, payment-failure-downgrade, cancellation, reactivation, AND webhook idempotency. Zero real-money charges (SC-007); zero orphan Stripe customers.

**Independent Test**: `pytest tests/e2e/journeys/test_j28_*.py tests/e2e/journeys/test_j32_*.py tests/e2e/journeys/test_j33_*.py tests/e2e/journeys/test_j34_*.py -m journey -n 4` against a Stripe test-mode account passes in ≤ 12 minutes; Stripe Customer Portal shows the expected subscription states; `purge_test_customers()` reports zero leaks at end.

### Implementation for User Story 2

- [X] T020 [P] [US2] Replace the skip-marked stub in `tests/e2e/journeys/test_j28_billing_lifecycle.py` (created by UPD-052) with five sub-scenario test functions sharing a module-scope fixture per `journey-template.md` § "Sub-scenario pattern": `test_j28_upgrade_free_to_pro`, `test_j28_overage_authorize_then_resume`, `test_j28_payment_failure_then_recovery`, `test_j28_payment_failure_then_grace_exhausted`, `test_j28_cancel_period_end_then_reactivate`. Uses Stripe test cards `pm_card_visa` (success), `pm_card_chargeDeclined` (failure), `pm_card_authenticationRequired` (3DS).
- [X] T021 [US2] Replace the skip-marked stub in `tests/e2e/journeys/test_j32_webhook_idempotency.py` (created by UPD-052) with the full body per spec.md US2 acceptance scenario 3 and FR-802. Triggers a real Stripe webhook event via `stripe.trigger_webhook(...)`, captures the event id, then calls `stripe.resend_webhook(event_id=...)` and asserts: HTTP 200 idempotency-key match in the response, no duplicate state mutation (subscription period not double-extended), audit chain shows exactly one `billing.invoice_paid` entry. Asserts the dedupe TTL ≥ 7 days by inspecting Redis key TTLs through the existing `redis_client` fixture.
- [X] T022 [US2] Replace the skip-marked stub in `tests/e2e/journeys/test_j33_trial_to_paid_conversion.py` (created by UPD-052) with the full body per spec.md FR-803. Uses Stripe Test Clock to advance: signup with 14-day trial, day-11 reminder notification (asserted via the existing notifications fixture), day-14 charge with `pm_card_visa`, status flip `trial`→`active`. Sub-test variant uses `pm_card_chargeDeclined`: status flips to `past_due` and grace begins.
- [X] T023 [US2] Replace the skip-marked stub in `tests/e2e/journeys/test_j34_cancellation_reactivation.py` (created by UPD-052) with the full body per spec.md FR-804. Cancels mid-cycle, asserts `cancellation_pending` and Pro features still available; reactivates before period-end and asserts `active`; second sub-scenario lets the period elapse and asserts `canceled` + downgrade-to-Free at next quota check. Includes the period-end race-window guard test from spec.md edge cases.

**Checkpoint**: all 4 US2 journeys pass; Stripe billing pipeline gated end-to-end.

---

## Phase 5: User Story 3 — Plans, quotas, and cost-protection (Priority: P2)

**Goal**: An engineer running `make e2e-saas-suite -- --suite plans_subscriptions` confirms quotas hard-cap Free, pause Pro on overage, and never trip Enterprise; that plan version edits are rejected and new-version-only is the mutation route; and that Free users provably cannot incur paid-tier cost.

**Independent Test**: `pytest tests/e2e/journeys/test_j23_*.py tests/e2e/journeys/test_j30_*.py tests/e2e/journeys/test_j37_*.py -m journey -n 4` passes in ≤ 8 minutes; ClickHouse cost-events table records zero charge for any Free-rejected attempt; plan-version-immutability test gets HTTP 409 on every edit attempt.

### Implementation for User Story 3

- [X] T024 [P] [US3] Create `tests/e2e/journeys/test_j23_quota_enforcement.py` per spec.md US3 acceptance scenario 1 and FR-793. Three sub-scenarios: Free hard-cap (HTTP 402 + `quota_exceeded` body, UI shows "Upgrade to Pro" CTA via Playwright), Pro overage (paused state + notification, then resume after authorize), Enterprise unlimited. Asserts counter reset on period boundary by manipulating the period-end timestamp through the existing test-clock helper.
- [X] T025 [P] [US3] Create `tests/e2e/journeys/test_j30_plan_versioning.py` per spec.md US3 acceptance scenario 2 and FR-800. Super-admin publishes Pro plan v2 (59 EUR); existing v1 (49 EUR) subscriber continues at 49 EUR; new signup lands on v2; edit attempt against v1 returns HTTP 409 `version_immutable`; opt-in upgrade emits a prorated invoice line, asserted ±1 cent against the documented prorated formula.
- [X] T026 [P] [US3] Create `tests/e2e/journeys/test_j37_free_plan_cost_protection.py` per spec.md US3 acceptance scenario 3 and FR-807. Three sub-scenarios: Free user invokes premium model → `quota_exceeded` BEFORE any model-router call (asserted via zero outbound `model_router_invocations_total` increment); oversize context request → rejected; many small executions until hard cap → HTTP 402. Period total cost asserted as 0 cents in ClickHouse `cost_events` table.

**Checkpoint**: all 3 US3 journeys pass; plans + quotas + cost-protection gated.

---

## Phase 6: User Story 4 — Marketplace, abuse prevention, and wildcard TLS renewal (Priority: P3)

**Goal**: An engineer running `make e2e-saas-suite -- --suite supporting` confirms the multi-scope marketplace visibility matrix, the four abuse-prevention defenses, and that wildcard TLS auto-renewal completes without service interruption. These journeys are P3 because the platform can ship to early customers without them being battle-tested, but they gate the SaaS-pass exit criteria.

**Independent Test**: `pytest tests/e2e/journeys/test_j25_*.py tests/e2e/journeys/test_j26_*.py tests/e2e/journeys/test_j35_*.py -m journey -n 4` passes in ≤ 10 minutes; marketplace visibility matches the spec's scope-and-flag matrix exactly; cert-renewal journey shows 100% HTTPS handshake success during renewal.

### Implementation for User Story 4

- [X] T027 [P] [US4] Create `tests/e2e/journeys/test_j25_marketplace_multi_scope.py` per spec.md US4 acceptance scenario 1 and FR-795. Provisions `acme` (with `consume_public_marketplace=true`) and `globex` (without). Default-tenant user publishes a `public_default_tenant` agent; super-admin approves; second default user runs it; `acme` user sees+runs read-only; `globex` user does NOT see it; tenant-scope agent inside `acme` is invisible from `globex` regardless of flag. Uses fixtures `tenants.provision_enterprise` × 2 + `users.synthetic_user` × 4.
- [X] T028 [P] [US4] Create `tests/e2e/journeys/test_j26_abuse_prevention.py` per spec.md US4 acceptance scenario 2 and FR-796. Four sub-scenarios: 10 signups same IP → velocity block at signup #10; disposable-email signup rejected pre-creation; suspended-account login blocked AND lifted-by-super-admin → re-login works; Free-tier premium-model + long-execution rejected pre-dispatch (cross-check with J37). Uses the existing rate-limit-aware `http_client` and the abuse-prevention BC's public `/admin/abuse/lift-suspension` endpoint.
- [X] T029 [US4] Replace the skip-marked stub in `tests/e2e/journeys/test_j35_wildcard_tls_renewal.py` (created by UPD-053) with the full body per spec.md US4 acceptance scenario 3 and FR-805. Sets `notAfter` 25 days into the future via cert-manager's testing endpoint, advances the renewal trigger; asserts cert-manager renews via the Hetzner DNS-01 webhook, the new cert is written to the same Secret name, ingress-nginx hot-reloads without dropping in-flight requests (parallel HTTPS load-tester running against `app.dev.musematic.ai` for the duration of the renewal). Variant: forced renewal failure → `WildcardCertRenewalFailing` Prometheus alert fires within 15 minutes.

**Checkpoint**: all 3 US4 journeys pass; marketplace + abuse + cert-renewal gated.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cross-suite verification, and the bookend tasks that close the SaaS-pass exit criteria.

- [X] T030 [P] Create `docs/operations/e2e-suite-maintenance.md` per `quickstart.md` § 8 and SC-009. Covers fixture lifecycle (per-test, idempotent teardown), parallel-runner architecture (4 xdist workers + the three filelock hot-spots), failure-artefact format (the four-pillar bundle), debugging the most common signatures from the quickstart's "Common pitfalls" table, and how to add a new journey.
- [X] T031 [P] Create the `saas-pass-soak.yml` GitHub Actions workflow per `contracts/promotion-gate.md` § "Soak-run extension (SC-006)" and quickstart.md § 7. Runs `make e2e-saas-soak` daily on `main`; on completion, runs `tests/e2e/scripts/verify_no_orphans.py` and posts a summary comment to a dedicated tracking issue. Does NOT block PR merges.
- [X] T032 [P] Run `python scripts/generate-env-docs.py --output docs/configuration/environment-variables.md` to pick up any new env vars introduced by the fixtures (`E2E_JOURNEY_WORKERS`, `STRIPE_TEST_MODE`, `RUN_J29`, `DNS_PROPAGATION_RESOLVER`). Commit the regenerated file. Verifies T032 doesn't break the existing `Docs staleness` CI gate.
- [X] T033 [P] Verify the SaaS-pass promotion gate trips on a deliberate journey failure (SC-004 acceptance). On a draft PR, mutate one assertion in `test_j22_tenant_provisioning.py` to fail; observe the `journey-tests (saas-pass)` required status check turn red; revert the mutation; observe it turn green. Document the steps in the new `e2e-suite-maintenance.md` runbook.
- [X] T034 Run `make e2e-saas-acceptance` against a freshly-deployed dev cluster end-to-end (manual operator step). Capture the wall-clock for the SC-002 baseline (≤ 30 min p95 for J22–J37 alone; ≤ 60 min for the full J01–J37 acceptance run). Record the result in the PR description.
- [X] T035 Run `make e2e-saas-soak` once locally to validate SC-006 (zero orphan resources after 100 runs) before relying on the nightly CI workflow to catch regressions.
- [X] T036 [P] Update the existing `tests/e2e/README.md` "Running journeys" section to reference the new `e2e-saas-suite` / `e2e-saas-acceptance` / `e2e-saas-soak` Makefile targets and the new `RUN_J29` opt-in flag. Cross-link to `docs/operations/e2e-suite-maintenance.md`.
- [X] T037 [P] Confirm `tools/verify_audit_chain.py` accepts the new audit-event types emitted by the journey runs (open-set; no allowlist update needed). Run once against the dev cluster's audit-chain after a full `e2e-saas-suite` run; the script's exit code MUST be 0.
- [X] T038 [P] Run `pnpm typecheck && pnpm lint` (frontend) — no changes expected, but the new Playwright a11y assertions (UPD-054 rule-28 ⚠️ flagged in plan.md) touch `apps/web` selectors and a typo in a `data-testid` would surface here.
- [X] T039 Cross-link the new `docs/operations/e2e-suite-maintenance.md` from `docs/operations/hetzner-cluster-provisioning.md` § "Related runbooks" so an operator landing on the cluster runbook can find the e2e debugging path.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories.
- **User Stories (Phases 3–6)**: All depend on Foundational completion. Within each story, journey tasks marked [P] can run in parallel; same-file edits MUST be sequential.
  - US1 → can start after Phase 2.
  - US2 → can start after Phase 2; can run in parallel with US1.
  - US3 → can start after Phase 2; can run in parallel with US1 and US2.
  - US4 → can start after Phase 2; can run in parallel with US1, US2, US3.
- **Polish (Phase 7)**: T030, T031, T036, T038, T039 [P] can start as soon as Phase 2 lands. T032, T037 wait for the journeys that introduce new env vars and audit events. T033, T034, T035 wait for all user stories to be merged so they exercise the complete suite.

### User Story Dependencies

- **US1 (P1)**: After Phase 2.
- **US2 (P2)**: After Phase 2; parallel with US1.
- **US3 (P2)**: After Phase 2; parallel with US1 and US2.
- **US4 (P3)**: After Phase 2; parallel with all others.

### Within Each User Story

- Each new journey lives in its own file → all `[P]` journey tasks within a story run in parallel.
- The four FILL-IN tasks (T016 J27, T017 J29, T020 J28, T021 J32, T022 J33, T023 J34, T029 J35) edit existing scaffold files; they are NOT marked [P] within their story because they touch shared scaffold imports during the rewrite. Tasks editing different scaffold files in the same story (e.g., T020 vs T021) ARE independent and can be parallelised across developers.
- The smoke-test contract enforcement (T011) MUST land before any new journey is committed; otherwise the smoke test will fail on the first journey PR.

### Parallel Opportunities

- All Phase 1 tasks are [P].
- All Phase 2 fixture tasks (T006, T007, T008, T009) are [P]; T010 (conftest wiring) follows them sequentially because it imports all four; T011 + T013 are [P] with each other.
- Cross-story parallelism: US1, US2, US3, US4 can all proceed in parallel by different developers; no cross-story import dependencies in the journey bodies.
- All Phase 7 docs/runbook tasks (T030, T031, T036, T038, T039) are [P].

---

## Parallel Example: User Story 1

```bash
# A team of three can split US1 three ways:
Task: "T014 [P] [US1] J22 tenant provisioning in tests/e2e/journeys/test_j22_tenant_provisioning.py"
Task: "T015 [P] [US1] J24 enterprise provisioning in tests/e2e/journeys/test_j24_enterprise_provisioning.py"
Task: "T018 [P] [US1] J31 cross-tenant isolation in tests/e2e/journeys/test_j31_cross_tenant_isolation.py"
Task: "T019 [P] [US1] J36 default tenant constraint in tests/e2e/journeys/test_j36_default_tenant_constraint.py"

# T016 (J27 fill-in) and T017 (J29 fill-in) sequentially per developer, since each
# rewrites a scaffold file end-to-end.
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Phase 1 setup (Stripe-cli install, Makefile targets, soak helper, verify-no-orphans).
2. Phase 2 foundational (4 fixtures + conftest + smoke-test extension + CI matrix entry + paths-filter).
3. Phase 3 US1 (6 tenant-correctness journeys).
4. **STOP and VALIDATE**: run `make e2e-saas-suite -- --suite tenant_architecture` against the dev cluster; assert SC-001 (zero failures) and a clean cleanup verification.
5. Deploy/demo if US1 acceptance passes — the platform is now demonstrably tenant-safe even before billing or marketplace surfaces are exercised.

### Incremental Delivery

1. Setup + Foundational → SaaS-pass framework ready.
2. US1 → tested + deployed (tenant correctness gated). MVP!
3. US2 → tested + deployed (billing pipeline gated).
4. US3 → tested + deployed (plans/quotas/cost-protection gated).
5. US4 → tested + deployed (marketplace + abuse + cert-renewal gated).
6. Polish → SaaS pass exit criteria (SC-001..SC-009) met.

Each user story adds independently testable validation without breaking the previous slices.

### Parallel Team Strategy

With 4 developers post-Phase-2:

- *Dev A*: US1 (tenant correctness) — owns the foundation and the most cross-cutting journeys.
- *Dev B*: US2 (billing) — owns the Stripe+webhook surface end-to-end.
- *Dev C*: US3 (plans/quotas/cost) — overlaps with Dev B on the Stripe fixture; coordinate fixture-only PRs first.
- *Dev D*: US4 (marketplace/abuse/TLS) — least coupled to billing; can run independently.

Phase 7 polish is a final shared sweep.

---

## Notes

- [P] tasks = different files, no dependencies.
- [Story] label maps task to specific user story for traceability.
- Each user story should be independently completable and testable.
- The six FILL-IN tasks (T016, T017, T020, T021, T022, T023, T029) replace existing skip-marked scaffolds left by UPD-052 / UPD-053; preserve the file path and pytestmark structure when rewriting.
- Commit after each task or logical group; the brownfield codebase prefers small reviewable commits.
- Stop at any checkpoint to validate the slice independently against `quickstart.md`.
- Avoid: vague tasks, same-file conflicts, cross-story import dependencies that break independence.
- Constitution Check (plan.md) verdict was PASS; this task list does not introduce any new violation surfaces.
