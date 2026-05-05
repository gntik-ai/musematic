# UPD-054 — Phase 0 Research

> Eight research items resolving the unknowns from the user-supplied implementation plan against the brownfield UPD-038 E2E framework. Each item: **Decision** → **Rationale** → **Alternatives considered**. Pre-existing scaffolds left by UPD-052 / UPD-053 are called out so the implementation phase fills them rather than recreating them.

---

## R1 — Stripe test-mode integration is a client wrapper, not a new SDK

**Decision**: The new `tests/e2e/fixtures/stripe.py` re-uses the existing `stripe>=11.0,<12` Python SDK already vendored in the control-plane runtime. It exposes a thin `StripeTestModeClient` whose `__init__` (a) reads the test API key from `secret/data/musematic/dev/billing/stripe/api-key` via the existing `SecretProvider` indirection, (b) refuses to construct if the resolved key prefix is `sk_live_`, and (c) wraps the SDK with helpers for: customer create + cleanup, subscription state inspection, clock-advance via the Stripe Test Clock API, and webhook trigger via `stripe-cli trigger`. Webhook *replay* (J32 idempotency) uses `stripe-cli events resend <event-id>` against a pre-captured event id.

**Rationale**: Constitution rule 11 (SecretProvider only) forbids `os.getenv` reads of credentials. The `SecretProvider` abstraction is already extended for test-mode in the control-plane Stripe code path. Using `stripe-cli` for webhook simulation is the canonical approach Stripe documents and is what the platform team already uses for ad-hoc testing — adopting it for automated testing is the path of least friction. Brownfield rule 4 (use existing patterns) — the fixture's `__repr__` redacts the API key the same way `dns_automation.HetznerDnsAutomationClient` already does for the Hetzner token.

**Alternatives considered**:
- *Vendor a separate Python wrapper around the Stripe REST API*: rejected — duplicates work the SDK already does and creates a maintenance liability when Stripe versions the API.
- *Mock all Stripe interaction in-process*: rejected — would not exercise webhook signing, dedupe TTL, or real subscription-status race conditions; defeats the purpose of E2E.
- *Use Stripe's Webhook Signing Local-Mode*: rejected — `stripe-cli trigger` already covers this and gives the same security guarantees with simpler ergonomics.

---

## R2 — DNS testing has two modes; mock is the default, live is opt-in

**Decision**: `tests/e2e/fixtures/dns.py` exposes two providers behind a single `DnsTestProvider` Protocol: `MockDnsProvider` (in-process state, no network, default) and `LiveHetznerDnsProvider` (gated by `RUN_J29=1`, scoped to a Hetzner DNS *test zone* — never the production `musematic.ai` zone). The Protocol surface mirrors `dns_automation.DnsAutomationClient` (UPD-053): `create_tenant_subdomain`, `remove_tenant_subdomain`, `verify_propagation`. The mock provider implements `verify_propagation` by reading its own internal state; the live provider polls a public resolver (`1.1.1.1`) and serializes calls per zone to stay under Hetzner's 1 req/s burst limit.

**Rationale**: Default-hermetic CI (SC-002 30-min p95) requires the mock path. Opt-in live coverage (operator runs with `RUN_J29=1` against a sandbox Hetzner project) catches regressions in the real DNS API surface. This mirrors UPD-053's existing E2E suite design — `tests/e2e/suites/hetzner_topology/test_dns_automation_create.py` already uses the same `RUN_J29` skip-marker convention, so the new journey just inherits it.

**Alternatives considered**:
- *Always live*: rejected — flakes, rate-limits, and a 5-minute propagation wait inside every CI run.
- *Always mocked*: rejected — never exercises real Hetzner API behaviour; latent regressions ship.
- *A third "kind-cluster CoreDNS" mode*: rejected — adds a third code path with marginal coverage gain over the in-process mock.

---

## R3 — Tenant lifecycle goes through the public admin API, not direct DB writes

**Decision**: `tests/e2e/fixtures/tenants.py` provisions Enterprise tenants via the public `POST /api/v1/admin/tenants` endpoint (UPD-053) and tears them down via `POST /api/v1/admin/tenants/{slug}/schedule-deletion` followed by `POST /api/v1/admin/tenants/{slug}/complete-deletion` (UPD-051 phase 2). No direct PostgreSQL inserts/deletes in fixture code. The fixture exposes `provision_enterprise(slug, plan, region) -> Tenant` and an async-context-manager pattern (`async with provision_enterprise(...) as tenant: ...`) that auto-cleans on exit.

**Rationale**: Constitution Brownfield rule 1 (never rewrite) and rule 4 (use existing patterns). The public admin API is the single source of truth for tenant lifecycle; bypassing it via SQL would let the test pass when the API is broken. Constitution principle IV (no cross-boundary DB access) — fixtures consume only the public surface.

**Alternatives considered**:
- *Direct asyncpg INSERT into `tenants` table*: rejected — bypasses RLS, audit chain, DNS automation, and Stripe customer creation; tests would green-light against a broken admin API.
- *Hand-cleanup at session end*: rejected — leaks if a test fails mid-fixture; the async-CM teardown is per-test and handles partial failures.
- *Fixture leaks the DB session for direct introspection*: rejected — the existing `db_session` fixture already provides this where needed; coupling the tenant fixture to the DB makes it harder to reuse.

---

## R4 — Synthetic users come from the existing accounts API, with deterministic email aliases

**Decision**: `tests/e2e/fixtures/users.py` creates synthetic users via the public signup or admin-invite endpoints (NOT direct DB inserts), with email aliases of the form `e2e-{j}-{role}-{uuid}@e2e.musematic-test.invalid`. The `.invalid` TLD guarantees the address is non-deliverable (RFC 2606) and the per-test UUID ensures uniqueness across parallel workers. The fixture wraps MFA enrollment via the existing TOTP test helpers (UPD-014) so a test that needs an MFA-enrolled user gets one in a single fixture call.

**Rationale**: The brownfield user-creation path through `accounts/router.py:signup` is the same code production runs; testing it via E2E exercises the full anti-enumeration + email validation + first-login flow. The `.invalid` TLD prevents accidental delivery if an email infrastructure misconfiguration exposes the test mailer. UUIDs in the local-part avoid the per-IP signup-velocity rule (J26's specific test) interfering with other journeys' fixture setups.

**Alternatives considered**:
- *Hard-coded email addresses*: rejected — collisions across parallel workers; per-IP rate-limit interference.
- *Direct DB INSERT into `accounts_users`*: rejected — same reason as R3; bypasses signup invariants.
- *A shared "fixture user pool" recycled across tests*: rejected — leaks state between tests; a failing teardown can poison the pool for the next worker.

---

## R5 — Promotion gate is a matrix dimension on the existing `journey-tests` job

**Decision**: Add a new entry to the `matrix.secret_mode` (or a parallel `matrix.suite`) of the existing `.github/workflows/ci.yml` `journey-tests` job rather than create a new workflow file. The new dimension runs `pytest tests/e2e/journeys/test_j2[2-9].py tests/e2e/journeys/test_j3[0-7].py -m journey -n 4` against the kind cluster brought up by the existing `Bootstrap kind cluster` step. Failure artefacts (screenshots, HARs, audit-chain dump) upload via the existing `actions/upload-artifact@v4` step; no new artefact bucket. The gate's required-status name is `journey-tests (saas-pass)`.

**Rationale**: The existing job already does kind-cluster + Helm + Stripe-cli setup; duplicating that in a new workflow file would inflate CI runner time and maintenance burden (research R7 from UPD-053 made the same call for the helm-lint snapshot gate). One required-status check is sufficient to enforce the SaaS-pass gate at branch protection.

**Alternatives considered**:
- *New `saas-pass-gate.yml` workflow file*: rejected — duplicate setup and maintenance.
- *Run the new journeys inline with J01–J21 in the existing matrix*: rejected — the SaaS journeys are heavier (Stripe clock-advance, DNS propagation polls) and would push the existing matrix entries over their soft timeout.
- *Run them only nightly*: rejected — that lets the SaaS-pass gate ride a slow signal; merging to `main` could break the SaaS pass for a full day before discovery.

---

## R6 — Failure artefacts use the existing UPD-038 capture pipeline

**Decision**: On any test failure, the suite emits four artefacts to `tests/e2e/reports/{run-id}/`: (a) Playwright HAR + screenshot from `playwright_capture()` already in the framework; (b) audit-chain slice for the test's correlation-id range from the existing `audit_chain_dump()` helper; (c) tenant-state JSON dump (subscriptions, DNS records, K8s Secrets) emitted by the new fixture's teardown-on-failure hook; (d) a journey-state log at `journey-state.json`. The CI step uploads `tests/e2e/reports/` as a single artefact named `e2e-saas-{matrix-id}-reports`.

**Rationale**: Reusing the four existing capture utilities is faster than designing new ones and matches what the platform team already knows how to read. SC-005 demands the artefact bundle is sufficient to triage 90% of failures; a four-pillar bundle (UI state, audit, system state, journey log) covers the cross-cutting nature of these tests.

**Alternatives considered**:
- *A single combined HTML report*: rejected — large reports are hard to host and harder to grep; four files in a directory are easier for operators to navigate.
- *Loki-only log aggregation*: rejected — Loki retention in dev is shorter than the failure investigation window; on-disk artefacts persist as long as the GitHub Actions retention does (90 days).
- *Slack-DM-on-failure*: rejected — out-of-scope for this feature; the platform team already has nightly digest tooling.

---

## R7 — `pytest-xdist` parallel workers, but with serialised hot-spots

**Decision**: The full SaaS suite runs with `pytest-xdist -n 4` by default. Three hot-spots serialise via the `pytest-xdist`-aware `filelock` pattern: (a) the Hetzner DNS zone (one writer at a time per zone, when in live mode); (b) the Stripe Test Clock for a given customer (one advance at a time); (c) the `tools/verify_audit_chain.py` invocation at session end. All other test paths run fully in parallel.

**Rationale**: SC-002's 30-min wall-clock p95 is unattainable single-threaded (~2-hour wall-clock per the spec assumption). Four workers gives ~30-min target with headroom; the hot-spots are narrow enough that serialisation costs don't dominate.

**Alternatives considered**:
- *Eight workers*: rejected — diminishing returns and increased Hetzner rate-limit pressure in live mode; 4 is the sweet spot for the runner spec assumed in the spec.
- *Per-test `redis lock`*: rejected — adds a Redis dependency to fixture init and complicates failure modes.
- *Single worker with shorter test bodies*: rejected — would miss whole-system race-condition coverage that comes from genuine parallel execution.

---

## R8 — Cleanup is per-fixture, idempotent, and verified by SC-006 soak

**Decision**: Every fixture's teardown (tenant deletion, user deletion, Stripe customer deletion, mock-DNS reset) is implemented as an idempotent operation that swallows "not found" responses and only raises on unexpected error codes. SC-006 is verified by a CI-only "soak" run (every commit on `main`, not per-PR) that runs the full suite 100 times in a tight loop and asserts zero orphan resources at the end via inspection helpers (`list_test_tenants()`, `list_test_stripe_customers()`, `list_test_dns_records()`).

**Rationale**: Brownfield rule 1 again (never rewrite) — the existing UPD-038 fixtures already use this pattern; we extend the convention. The 100-run soak catches the long-tail flake where cleanup *almost* always succeeds but leaks once every 50 runs; a one-off run would not.

**Alternatives considered**:
- *Per-PR soak*: rejected — adds 60+ minutes to PR CI; the bug class it catches is not blocking individual merges.
- *Skip soak entirely*: rejected — silent leaks accumulate across thousands of CI runs, eventually breaking shared fixtures (e.g., Stripe test-mode rate limits per account).
- *Per-test cleanup verification*: rejected — would slow every CI run by 30-60 seconds.

---

*All NEEDS CLARIFICATION resolved. Phase 1 (data-model + contracts + quickstart) follows.*
