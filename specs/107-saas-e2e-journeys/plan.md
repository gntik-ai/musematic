# Implementation Plan: UPD-054 — SaaS E2E Journey Tests

**Branch**: `107-saas-e2e-journeys` | **Date**: 2026-05-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/107-saas-e2e-journeys/spec.md`

## Summary

Closes the SaaS pass exit criteria by adding **16 new end-to-end journeys (J22–J37)** to the existing UPD-038 test framework. The work is overwhelmingly *test code* — no new BCs, no DDL, no new Kafka topics, no new Vault path families, no new REST endpoints. The plan extends the four assets the framework is currently missing:

1. Four new fixtures under `tests/e2e/fixtures/` — `tenants.py` (programmatic Enterprise tenant create/teardown via the UPD-053 admin API), `users.py` (synthetic users with tenant binding and MFA setup), `stripe.py` (Stripe-test-mode client + `stripe-cli` webhook replay + clock-advance), `dns.py` (mock by default, real Hetzner test zone gated by `RUN_J29=1`).
2. **Sixteen journey test bodies** filling 10 brand-new scaffolds (J22, J23, J24, J25, J26, J30, J31, J35, J36, J37) and 6 already-skip-marked scaffolds left by UPD-052 / UPD-053 (J27, J28, J29, J32, J33, J34).
3. **CI promotion gate** — an extension of the existing `journey-tests` job in `.github/workflows/ci.yml` so the full `J22–J37` set runs on every PR touching the SaaS surface and blocks merge to `main` on any failure. Existing J01–J21 invocations continue unchanged.
4. **Operator runbook** at `docs/operations/e2e-suite-maintenance.md` covering fixture lifecycle, parallel-runner architecture, failure-artefact format, and common debugging steps.

The full SaaS pass passes when J01–J37 (37 journeys total) green-light on the dev cluster.

## Technical Context

**Language/Version**: Python 3.12 (test framework + fixtures), TypeScript 5.x (Playwright scripts where the journey crosses into the Next.js UI). No new languages.
**Primary Dependencies (existing, reused)**: pytest 8.x + pytest-asyncio + pytest-html + pytest-timeout + pytest-xdist (parallel workers, already added by UPD-038); httpx 0.27+; websockets; Playwright 1.46+ (Python bindings); aiokafka 0.11+; asyncpg 0.29+ (test-DB inspection only); python-on-whales (kind-cluster lifecycle); aioboto3 (MinIO inspection); the existing UPD-038 fixtures (`http_client`, `ws_client`, `db_session`, `kafka_consumer`, `workspace`, `agent`, `policy`, `mock_llm`).
**Primary Dependencies (NEW)**:
- *Python*: `stripe>=11.0,<12` already in the control-plane runtime — re-export through the new `tests/e2e/fixtures/stripe.py` so journeys consume a thin Stripe-test-mode client; **no new pip dependency required**.
- *External binaries*: `stripe-cli` (CI installs from GitHub release; local devs from Homebrew). Used for webhook replay (J32) and trigger fixtures (J28, J33).
- *Optional*: `dnspython>=2.6` (already a transitive of cert-manager-related tooling) for resolver helpers; pulled in only if the dns fixture's mock path can't be used.
**Storage**:
- **PostgreSQL** — read-only inspection from journey tests via the existing `db_session` fixture. No DDL. No new tables. Tenant cleanup is performed via the public `DELETE /api/v1/admin/tenants/{slug}` endpoint, not direct DB writes (Brownfield rule 1).
- **Redis** — no test-only keys. Test isolation comes from per-test tenant slugs.
- **Kafka** — no new topics. Journey tests consume from `tenants.events`, `accounts.events`, `billing.events`, `marketplace.events` via the existing `kafka_consumer` fixture.
- **MinIO / S3** — read-only inspection of `tenant-dpas`, `tenant-data-exports`, `marketplace-artifacts` via `aioboto3`. No new buckets.
- **Vault** — read-only access to existing test-mode Stripe credentials at `secret/data/musematic/dev/billing/stripe/api-key` and `secret/data/musematic/dev/billing/stripe/webhook-secret`. No new path family.
- **Hetzner DNS** — optional live-mode access via `secret/data/musematic/dev/dns/hetzner/api-token` (UPD-053 path); mocked by default.
**Testing**:
- *New tests* live under `tests/e2e/journeys/test_j2X.py` and `test_j3X.py`. Each journey owns one file; test functions inside use `@pytest.mark.journey` and the `@pytest.mark.j_NN` filter so a single suite invocation can target one journey.
- *Coverage*: rule 14 (≥95%) does not apply to E2E tests (the rule is unit-test scoped). The acceptance gate for this feature is the SC-001 / SC-002 / SC-003 success criteria.
- *Stripe* fixture writes ONLY to test-mode (`sk_test_*`); a guard at fixture init refuses to run if the resolved key starts with `sk_live_`.
- *DNS* fixture has two modes: `mock` (in-process state, no network) and `live` (real Hetzner test zone, opt-in via `RUN_J29=1`). The matrix is documented in `tests/e2e/fixtures/dns.py`'s docstring.
**Target Platform**: Local kind-cluster (developer laptop) and the existing `journey-tests` GitHub Actions job. No new runtime profile.
**Project Type**: Test-suite extension of the brownfield Python control-plane + Next.js frontend monorepo.
**Performance Goals**: SC-002 — full SaaS suite (J22–J37) ≤ 30 min wall-clock p95 on a runner with ≥ 4 parallel workers, ≥ 8 vCPU, ≥ 16 GiB RAM. Single-worker fall-back ≈ 2 hours, intended for local debugging.
**Constraints**:
- **Hetzner DNS rate limits** — 1 req/s burst per token. The `dns.py` fixture serializes per-zone calls when in live mode (FR-A from spec edge cases).
- **Stripe test-mode webhook replay window** — 7 days. The J32 idempotency test asserts the dedupe TTL covers this.
- **Cleanup idempotence** — every fixture's teardown MUST be re-runnable; SC-006 is verified by a 100-journey soak run.
- **No real-money charges** (SC-007) — Stripe fixture init refuses non-test-mode keys; CI environment lacks production Stripe credentials.
- **Audit-chain integrity** — verified once per suite at the end via `tools/verify_audit_chain.py`, not per-test (chain is a single global ledger).
- **8-minute per-journey hard timeout** — `pytest-timeout` plug-in enforces; on timeout a fixture-state dump is emitted before the SIGKILL.
**Scale/Scope**:
- 4 new fixture modules (~150 LOC each).
- 16 new journey test files (~200 LOC each on average; J28 the heaviest at ~400 LOC because it carries five sub-scenarios).
- 1 new operator runbook (~250 lines).
- 0 lines of frontend changes; 0 lines of control-plane source changes; 0 lines of Helm changes; 0 lines of CI source changes beyond appending the new journeys to the existing matrix in `.github/workflows/ci.yml:419 (journey-tests)`.

## Constitution Check

Mapped to Constitution v1.3.0 principles I–XVI plus the brownfield + audit-pass rules. One verdict per gate; gaps tracked in **Complexity Tracking**.

| Principle / Rule | Verdict | Notes |
|---|---|---|
| **I. Modular Monolith** | ✅ | No new BC. All new code lives under `tests/e2e/`. |
| **II. Go Reasoning Engine separate** | N/A | No Go work. |
| **III. Dedicated data stores** | N/A | No data store changes. |
| **IV. No cross-boundary DB access** | ✅ | Journeys mutate state ONLY via public REST/WS endpoints (the admin API for tenant lifecycle, the user API for everything else). Direct DB reads are inspection-only via the existing `db_session` fixture. |
| **V. Append-only execution journal** | N/A | Not a workflow runtime feature. |
| **VI. Policy is machine-enforced** | ✅ | The journey tests *exercise* policy enforcement (J23 quota, J26 abuse, J36 default-tenant immutability) but do not author policy. |
| **VII. Simulation isolation** | N/A | |
| **VIII. FQN addressing** | N/A | |
| **IX. Zero-trust default visibility** | ✅ | J31 explicitly verifies it. |
| **X. GID correlation** | ✅ | Journey HTTP requests include the existing correlation-id header convention; assertions on audit-chain entries cross-reference the correlation id. |
| **XI. Secrets never in LLM context** | ✅ | Stripe + DNS tokens are read by the fixture and never echoed into journey logs (a redaction guard in the fixture's `__repr__` enforces this). |
| **XII. Task plans persisted** | N/A | |
| **XIII. Attention pattern** | N/A | |
| **XIV. A2A** | N/A | |
| **XV. MCP** | N/A | |
| **XVI. Generic S3** | ✅ | The fixture inspecting tenant exports uses the generic-S3 client (`S3_ENDPOINT_URL` etc.). |
| **Brownfield rule 1 (never rewrite)** | ✅ | All four fixture modules are NEW additions; the existing eight fixtures are imported, never rewritten. The six already-skip-marked journey scaffolds (J27/J28/J29/J32/J33/J34) get filled-in *bodies*; their pytest-marker scaffolding is preserved verbatim. |
| **Brownfield rule 2 (every change is an Alembic migration)** | ✅ | No DDL; no migration. |
| **Brownfield rule 3 (preserve tests)** | ✅ | J01–J21 continue to run unchanged in CI's existing `journey-tests` matrix; SC-003 verifies. |
| **Brownfield rule 4 (use existing patterns)** | ✅ | Fixture style mirrors `tests/e2e/fixtures/workspace.py`; journey style mirrors `test_j01_admin_bootstrap.py`. |
| **Brownfield rule 5 (cite exact files)** | ✅ | Every modified or created file is named in the Project Structure section below. |
| **Brownfield rule 6 (additive enums)** | N/A | No enum changes. |
| **Brownfield rule 7 (backward-compatible APIs)** | ✅ | No API changes. |
| **Brownfield rule 8 (feature flags)** | ✅ | The two opt-in modes (live Hetzner DNS, live Stripe test-mode replay) are env-flag-gated (`RUN_J29=1`, `STRIPE_REPLAY=1`) so the default invocation is hermetic. |
| **Rule 9 audit chain integrity** | ✅ | `tools/verify_audit_chain.py` is invoked once per suite run (after all journeys complete) per the spec edge case. |
| **Rule 14 ≥95% coverage** | N/A | E2E suite is acceptance-tested via SC-001..SC-009, not line coverage. |
| **Rule 15 BC boundary** | ✅ | No source-tree changes outside `tests/e2e/` and `docs/operations/`. |
| **Rule 17 outbound webhooks HMAC-signed** | N/A | This feature has no outbound webhooks; the Stripe fixture *consumes* webhooks. |
| **Rule 25 E2E suite + journey crossing** | ✅ | This *is* the rule-25 implementation for the SaaS pass. Each new journey crosses ≥ 2 BCs (J28: billing ↔ accounts ↔ tenants; J22: tenants ↔ accounts ↔ DNS ↔ TLS; J31: tenants ↔ workspaces ↔ governance; etc.). |
| **Rule 26 real observability backends in journey tests** | ✅ | Journeys run against the kind cluster with the full observability stack (Prometheus + Grafana + OTEL collector) installed via UPD-047. Failure-artefact bundle includes Prometheus snapshots and Loki log slices. |
| **Rule 28 a11y tested** | ⚠️ | Journeys that touch the UI (J22 setup wizard, J28 upgrade, J34 cancel-reactivate) include a Playwright `axe-core` pass on their critical screens. This is additive; full-app a11y remains owned by the dedicated UPD-083 a11y suite. |
| **Rule 33 2PA enforced server-side** | ✅ | J22 / J27 exercise the 2PA flow via the public super-admin endpoints; no test-only bypass. |
| **Rule 49 outage independence** | ✅ | J35 (wildcard TLS renewal) verifies cert-manager auto-renewal without service interruption. |
| **Rule 50 mock LLM in creator previews** | ✅ | Journeys that invoke an agent consume the existing `mock_llm` fixture; no real model calls. |

**Constitution Check verdict**: PASS. The only ⚠️ is rule 28 (a11y) — flagged because UPD-083 owns full-app a11y; UPD-054 only tests the screens its journeys touch. No new violation surface.

## Project Structure

### Documentation (this feature)

```text
specs/107-saas-e2e-journeys/
├── plan.md                       # This file
├── research.md                   # Phase 0 — decisions on fixture design + harness boundaries
├── data-model.md                 # Phase 1 — no DDL; references the brownfield models the journeys touch
├── quickstart.md                 # Phase 1 — operator runbook (dev-cluster bring-up + suite invocation)
├── contracts/
│   ├── tenants-fixture.md        # Programmatic tenant create/teardown contract
│   ├── stripe-fixture.md         # Stripe test-mode client + webhook replay contract
│   ├── dns-fixture.md            # Mock vs live DNS provider contract
│   ├── promotion-gate.md         # CI gate behaviour and failure-artefact format
│   └── journey-template.md       # The shape every journey test must follow (markers, fixtures, cleanup)
├── checklists/
│   └── requirements.md
└── tasks.md                      # Phase 2 (/speckit-tasks command — NOT created here)
```

### Source Code (repository root)

```text
tests/e2e/
├── fixtures/
│   ├── tenants.py                # NEW — provision_enterprise(slug, plan, region) + teardown
│   ├── users.py                  # NEW — synthetic_user(tenant, role, mfa=...)
│   ├── stripe.py                 # NEW — Stripe-test-mode client, test cards, webhook-cli replay,
│   │                             #         clock-advance helpers
│   ├── dns.py                    # NEW — mock/live providers; per-zone serialization; resolver poll
│   ├── http_client.py            # UNCHANGED (existing)
│   ├── ws_client.py              # UNCHANGED
│   ├── db_session.py             # UNCHANGED
│   ├── kafka_consumer.py         # UNCHANGED
│   ├── workspace.py              # UNCHANGED
│   ├── agent.py                  # UNCHANGED
│   ├── policy.py                 # UNCHANGED
│   └── mock_llm.py               # UNCHANGED
├── journeys/
│   ├── test_j22_tenant_provisioning.py        # NEW
│   ├── test_j23_quota_enforcement.py          # NEW
│   ├── test_j24_enterprise_provisioning.py    # NEW
│   ├── test_j25_marketplace_multi_scope.py    # NEW
│   ├── test_j26_abuse_prevention.py           # NEW
│   ├── test_j27_tenant_lifecycle_cancellation.py  # FILL-IN (scaffold from UPD-052)
│   ├── test_j28_billing_lifecycle.py          # FILL-IN (scaffold from UPD-052)
│   ├── test_j29_hetzner_topology.py           # FILL-IN (scaffold from UPD-053)
│   ├── test_j30_plan_versioning.py            # NEW
│   ├── test_j31_cross_tenant_isolation.py     # NEW
│   ├── test_j32_webhook_idempotency.py        # FILL-IN (scaffold from UPD-052)
│   ├── test_j33_trial_to_paid_conversion.py   # FILL-IN (scaffold from UPD-052)
│   ├── test_j34_cancellation_reactivation.py  # FILL-IN (scaffold from UPD-052)
│   ├── test_j35_wildcard_tls_renewal.py       # FILL-IN (scaffold from UPD-053)
│   ├── test_j36_default_tenant_constraint.py  # NEW
│   └── test_j37_free_plan_cost_protection.py  # NEW
└── README.md                                 # EXTEND — add a "SaaS pass — J22-J37" section

.github/workflows/
└── ci.yml                                   # EXTEND — extend the existing `journey-tests` job
                                             #   matrix to include the new SaaS suite slice and
                                             #   wire the failure-artefact upload step

docs/operations/
└── e2e-suite-maintenance.md                 # NEW — fixture lifecycle, debugging guide, cleanup procedures

Makefile
└── e2e-saas-suite + e2e-saas-acceptance     # EXTEND — two new convenience targets per quickstart
```

**Structure Decision**: This is a **test-suite extension** of the brownfield repo. No source-tree files outside `tests/e2e/`, `docs/operations/`, `.github/workflows/ci.yml`, and the root `Makefile` are touched. No new bounded context. No DDL. No Kafka topic. The plan exists primarily to extend the UPD-038 framework with four fixtures and sixteen journey bodies; the brownfield E2E surface (kind-cluster bootstrap, Playwright wiring, parallel runner via `pytest-xdist`, failure-artefact upload to the existing CI artefact bucket) is reused unchanged.

## Complexity Tracking

| Violation / Choice | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| **Two opt-in modes for Stripe and DNS** | Live external services would make the default CI run flaky and slow; mocked default keeps PR CI fast and hermetic; opt-in mode lets the platform team validate live integrations on a cadence (e.g., nightly). | Force-live: rejected — CI rate-limits + cost; SC-002 30-min p95 unattainable. Force-mock: rejected — never exercises the real Stripe webhook signing or Hetzner DNS rate-limiter, leaving regressions latent. |
| **Per-journey 8-minute hard timeout via pytest-timeout** | Some journeys (J22 with the 5-minute DNS-propagation step + the MFA setup wizard) approach 5 minutes; without a hard timeout a stuck fixture would block CI for the full job timeout (60 min). | Soft timeout per step: rejected — many existing fixtures don't expose step-level deadlines; coarse hard kill at the journey level is simpler and still emits the fixture-state dump. |
| **Dedicated `e2e-suite-maintenance.md` runbook instead of expanding the existing E2E `README.md`** | The maintenance + debugging surface (fixture lifecycle, cleanup procedures, failure-artefact dissection, parallel-runner architecture) is large enough that folding it into the existing README would dilute the "how do I run the tests" entry point. The new file is cross-linked from the README. | Single README: rejected — would push the README past 500 lines and bury the quick-start. |
| **Cleanup is fixture-owned, not session-owned** | The brownfield framework prefers per-test cleanup (each fixture's `yield` returns to teardown) over session-end sweeps. This keeps tests isolatable and re-runnable; a session-end sweep would leak between failing tests. | Session-end sweep: rejected — masks per-test cleanup bugs and breaks `pytest-xdist` parallelism (workers don't share session). |
| **Promotion gate as an extension of `journey-tests`, not a new workflow file** | The existing `journey-tests` job already provisions the kind cluster, sets up Helm, and uploads artefacts. A separate `saas-pass-gate.yml` would duplicate every one of those setup steps for marginal isolation gain. | New workflow: rejected — duplicate setup, duplicate maintenance burden. The new SaaS slice runs as an additional matrix dimension inside the existing job. |

---

*Phase 0 (research) and Phase 1 (data-model + contracts + quickstart) artefacts are emitted as siblings to this file. Phase 2 (tasks.md) is generated by `/speckit-tasks` and is intentionally not produced here.*
