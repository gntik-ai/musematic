# Implementation Plan: UPD-050 — Abuse Prevention and Trust & Safety (Refresh on 100-upd-050-abuse)

**Branch**: `103-abuse-prevention` | **Date**: 2026-05-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/103-abuse-prevention/spec.md`

## Summary

UPD-050 adds the abuse-prevention layer that protects the public default tenant from bot signups, free-tier cost mining, credential stuffing, and disposable-email churn. The implementation is **additive** behind a new bounded context at `apps/control-plane/src/platform/security/abuse_prevention/` that wraps:

- a Redis-backed velocity rate limiter (per IP, ASN, email domain)
- a database-backed disposable-email registry with weekly upstream sync
- an `account_suspensions` aggregate with auto-suspension rule engine
- an `abuse_prevention_settings` key/value store driving the admin surface
- a CAPTCHA verifier (Cloudflare Turnstile primary, hCaptcha alternate)
- optional GeoLite2-driven geo-blocking
- optional fraud-scoring adapter Protocols (no provider implementations shipping in this branch)
- runtime-side cost-protection enforcement that reads UPD-047 plan fields (`allowed_model_tier`, `max_execution_time_seconds`, `max_reasoning_depth`, `monthly_execution_cap`)

A new admin surface at `/admin/security/*` lets the super admin tune thresholds, review suspensions, and override the disposable-email list.

The signup endpoint at `apps/control-plane/src/platform/accounts/router.py:72` (`POST /api/v1/accounts/register`) gains five guards in order (velocity → disposable-email → CAPTCHA → geo-block → fraud-scoring) before it reaches the existing `AccountsService.register`. Each guard is independently toggleable by super-admin setting; default thresholds and toggles ship safe (velocity + disposable-email on, CAPTCHA + geo-block + fraud-scoring off).

The login path at `apps/control-plane/src/platform/auth/` gains a suspension-state check that produces the humanised "suspended pending review" response per FR-744.5.

### Refresh-pass deltas relative to the prior `100-upd-050-abuse` branch

This plan supersedes the unmerged `100-upd-050-abuse` branch on three concrete points:

1. **Migration number**: `110_abuse_prevention` (the prior branch's `109_abuse_prevention` is no longer available — `109` is now taken by `109_marketplace_reviewer_assign` from PR #135, UPD-049 refresh). The Alembic revision id is `110_abuse_prevention` (≤32 chars per the `alembic_version.version_num varchar(32)` constraint we just learned in PR #135).
2. **Bounded-context path**: `apps/control-plane/src/platform/security/abuse_prevention/` (the prior branch used `security_abuse/` with no nested subpackage). The user input for this refresh names the nested layout, and we adopt it. If the prior branch's code is later cherry-picked, files must be moved.
3. **Module split**: the prior branch used a single `service.py` for both disposable-emails and suspension. This refresh splits them into `disposable_emails.py` and `suspension.py` per the user input — each domain gets its own service.

All other prior-pass design decisions (Redis-backed counters, weekly cron, Turnstile-as-primary, Protocol-based fraud-scoring, settings-driven feature flags, signup-endpoint guard ordering) are inherited.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js admin UI), SQL (Alembic Python migration targeting PostgreSQL 16)
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, redis-py 5.x async (velocity counters + CAPTCHA-token-replay cache), aiokafka 0.11+ (audit-chain projection events), httpx 0.27+ (CAPTCHA verification + fraud-scoring adapter calls), APScheduler 3.x (disposable-email sync cron + auto-suspension rule scanner), `geoip2` 4.x (NEW — MaxMind GeoLite2 reader; pure Python, ~1.5 MB DB asset), pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict; frontend reuses the existing Next.js + shadcn/ui stack — no new packages.
**Storage**: PostgreSQL — Alembic migration 110 adds 6 new tables (`signup_velocity_counters` durable mirror, `disposable_email_domains`, `disposable_email_overrides`, `trusted_source_allowlist`, `account_suspensions`, `abuse_prevention_settings`); Redis — 4 new key families (`abuse:vel:ip:{ip}` rolling-hour counter, `abuse:vel:asn:{asn}` rolling-hour counter, `abuse:vel:domain:{domain}` rolling-day counter, `abuse:captcha_seen:{token_hash}` 10-min replay cache); MinIO not used by this feature; the GeoLite2 DB ships as a chart-mounted ConfigMap (or a Helm-time download into a Job-prepared PVC).
**Testing**: pytest + pytest-asyncio for backend (unit + integration + migration smoke); Vitest + Playwright for frontend admin UI; the integration_live mark from PR #135 covers live-DB tests for cross-process behaviours (suspension session-revocation, cron-driven list refresh).
**Target Platform**: Linux (Kubernetes via Helm chart); local dev via `make dev-up`.
**Project Type**: Web service — Python control plane + Next.js admin UI.
**Performance Goals**: SC-006 — fraud-scoring outage adds ≤200 ms to signup p95; velocity check adds ≤5 ms p99 (Redis INCR + EXPIRE); disposable-email lookup adds ≤2 ms p99 (in-memory cache, refreshed hourly from PostgreSQL).
**Constraints**: Velocity counters MUST fail-closed on Redis outage to preserve abuse protection (refusing the request is safer than letting an unbounded queue through); disposable-email override list NEVER exposed publicly; suspension reasons NEVER leaked verbatim to suspended users — the user-facing message identifies "account suspended" as the cause and points to the appeal route, but specific evidence stays in the audit chain (FR-744.5 says the refusal MUST NOT be indistinguishable from a generic credential failure, but the *reason detail* stays internal); IP/ASN identifiers are hashed once their counter window expires per privacy note in user input.
**Scale/Scope**: 6 new database tables, ~14 new Pydantic schemas, ~10 new exception classes, 4 new Kafka event types on a new `security.abuse_events` topic (`abuse.signup.refused`, `abuse.suspension.applied`, `abuse.suspension.lifted`, `abuse.threshold.changed`), 1 new Alembic migration (110), ~14 new REST endpoints (1 extension to `/api/v1/accounts/register` + 13 admin-surface endpoints under `/api/v1/admin/security/*`), 2 new APScheduler crons (disposable-email sync weekly + auto-suspension scanner every 5 min), 1 new fan-out for runtime cost-protection enforcement integrated at `model_router`, `execution_service`, and `reasoning_engine`.

## Constitution Check

> *GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.3.0 governs UPD-023–UPD-045. UPD-050 sits in the SaaS Transformation Pass (UPD-046–UPD-054), post-audit-pass. The relevant binding rules:

- **Brownfield rule 1 (never rewrite)**: ✅ additive — new bounded context, new migration, new admin router; the existing `accounts/router.py` register endpoint gains pre-guards rather than a rewrite.
- **Brownfield rule 2 (every change is an Alembic migration)**: ✅ migration 110.
- **Brownfield rule 3 (preserve all existing tests)**: ✅ no deletions; new tests under `tests/unit/security/abuse_prevention/` and `tests/integration/security/abuse_prevention/`.
- **Brownfield rule 4 (use existing patterns)**: ✅ FastAPI router, Pydantic schemas, SQLAlchemy mixins, Kafka envelope, audit-chain, APScheduler crons, AlertService (UPD-042), AsyncRedisClient — all reused.
- **Brownfield rule 5 (reference existing files)**: ✅ this plan cites exact paths (`accounts/router.py:72` for the register endpoint, `auth/` for the suspension check, `notifications/dependencies.py` for AlertService).
- **Brownfield rule 6 (additive enum values)**: ✅ no enum changes — `account_suspensions.reason` is `VARCHAR(64)` with a CHECK constraint over a documented string set.
- **Brownfield rule 7 (backward-compatible APIs)**: ✅ the register endpoint keeps its existing request shape; `captcha_token` is an optional field that becomes required only when the super-admin setting flips CAPTCHA on.
- **Brownfield rule 8 (feature flags)**: ✅ all four optional layers (CAPTCHA, geo-block, fraud-scoring, GeoLite2 DB presence) are controlled by `abuse_prevention_settings` rows, not deploy-time flags — operations can flip them in real time without a redeploy.
- **Rule 9 (audit-chain via service)**: ✅ all abuse-prevention decisions emit audit-chain entries via `security_compliance/services/audit_chain_service.py`; no direct writes.
- **Rule 10 (vault for secrets)**: ✅ CAPTCHA provider secret keys and fraud-scoring API keys resolved via the existing `SecretProvider` per rule 39.
- **Rule 12 (cost attribution)**: ✅ runtime-side cost-protection enforcement does NOT introduce new cost paths — it refuses paths that would otherwise emit cost attributions.
- **Rule 18 (regional queries enforce data residency)**: ✅ velocity counters and the disposable-email cache are not cross-region; geo-IP lookups are read-only against an embedded DB.
- **Rule 22 (Loki low-cardinality labels)**: ✅ IP/ASN go in JSON payload, not as Loki labels (high-cardinality).
- **Rule 23 (secrets never reach logs)**: ✅ CAPTCHA tokens, fraud-scoring API keys never logged.
- **Rule 24 (every new BC gets a Grafana dashboard)**: ✅ `deploy/helm/observability/templates/dashboards/abuse-prevention.yaml` ships as a ConfigMap with `grafana_dashboard: "1"`.
- **Rule 25 (every new BC gets an E2E suite + journey crossing)**: ✅ `tests/e2e/suites/abuse_prevention/` + J26 journey covering all 5 user stories.
- **Rule 26 (E2E uses real backends, not mocks)**: ✅ velocity/suspension tests run against the kind cluster's Redis + Postgres + Kafka; CAPTCHA and fraud-scoring adapters use mock servers because real Turnstile/minFraud calls are out of scope for CI.
- **Rule 29 (admin endpoint segregation)**: ✅ all new endpoints under `/api/v1/admin/security/*`, tagged `admin.security_abuse_prevention` in OpenAPI, with their own rate-limit group.
- **Rule 30 (admin role gate per route)**: ✅ every method depends on `require_superadmin`.
- **Rule 36 (every new FR with UX impact must be documented)**: ✅ `docs/admin-guide/abuse-prevention.md` is added with operator walkthroughs.
- **Rule 37 (env vars + Helm values + feature flags auto-documented)**: ✅ no new env vars; new Helm values for the GeoLite2 DB ConfigMap are auto-documented by `helm-docs` as part of CI.
- **Rule 39 (every secret resolves via SecretProvider)**: ✅ no `os.getenv` for secret patterns outside `SecretProvider` files.
- **Rule 41 (Vault failure does not bypass authentication)**: ✅ if Vault is unreachable, signup fails closed (cannot resolve CAPTCHA secret) — consistent with constitutional default.
- **Rule 47 (workspace-vs-platform scope distinction)**: ✅ abuse-prevention is platform-scoped; settings live in a single platform-wide table; no workspace-scoped duplicates.
- **Rule 48 (platform state is user-visible)**: ✅ a suspended user sees the suspension state explicitly via the login refusal.
- **AD-19 (provider-agnostic model routing)**: ✅ Free-tier cost protection enforces `allowed_model_tier` at the model-router level, not at provider SDKs.
- **AD-20 (per-execution cost attribution)**: ✅ refused executions do not attribute cost (correctly — there is no cost to attribute).

UPD-050 also adds three SaaS-pass-specific architectural decisions documented inline (already in spec Assumptions; this plan inherits them):

- **Privileged-role exemption from auto-suspension**: hard rule encoded in the auto-suspension service.
- **Velocity counters fail-closed on Redis outage**: refusing is safer than admitting an unbounded burst.
- **Disposable-email override list is platform-private**: never exposed via any API to non-super-admin callers.

**Constitution Check verdict: PASS.** No violations to justify. Complexity Tracking section intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/103-abuse-prevention/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # /speckit-specify output
├── research.md          # Phase 0 — research decisions
├── data-model.md        # Phase 1 — 6 new tables, 4 Redis key families
├── quickstart.md        # Phase 1 — operator + super-admin walkthroughs (5 flows)
├── contracts/           # Phase 1 — REST + Kafka contracts
│   ├── signup-guards-rest.md
│   ├── admin-abuse-prevention-rest.md
│   ├── suspension-rest.md
│   ├── disposable-email-overrides-rest.md
│   ├── geo-policy-rest.md
│   └── abuse-events-kafka.md
├── checklists/
│   └── requirements.md  # Spec-quality checklist (created by /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created by /speckit-plan)
```

### Source Code (repository root — modified or added by this feature)

```text
apps/control-plane/
├── migrations/versions/
│   └── 110_abuse_prevention.py                    # NEW — single migration, 6 tables + seed defaults
├── src/platform/
│   ├── security/
│   │   └── abuse_prevention/                      # NEW — bounded context (nested under security/)
│   │       ├── __init__.py
│   │       ├── models.py                          # SQLAlchemy models for 6 tables
│   │       ├── schemas.py                         # ~14 Pydantic schemas
│   │       ├── repository.py                      # SQLAlchemy queries
│   │       ├── service.py                         # AbusePreventionService (settings + audit)
│   │       ├── velocity.py                        # Redis-backed counters
│   │       ├── disposable_emails.py               # registry + cache + cron
│   │       ├── suspension.py                      # SuspensionService + auto-rule engine
│   │       ├── captcha.py                         # Turnstile + hCaptcha adapter via Protocol
│   │       ├── geo_block.py                       # GeoLite2 reader
│   │       ├── fraud_scoring.py                   # pluggable Protocol adapter
│   │       ├── consumer.py                        # Kafka consumer (cost-burn-rate auto-suspension)
│   │       ├── cron.py                            # APScheduler bindings
│   │       ├── events.py                          # 4 new Kafka event types + payloads
│   │       ├── exceptions.py                      # 10 new error classes
│   │       ├── metrics.py                         # Prometheus counters
│   │       ├── dependencies.py                    # FastAPI dependency builders
│   │       └── admin_router.py                    # /api/v1/admin/security/* endpoints
│   ├── accounts/
│   │   └── router.py                              # MODIFIED — add 5 guards before AccountsService.register
│   ├── auth/
│   │   ├── service.py                             # MODIFIED — login refuses on active suspension
│   │   └── dependencies.py                        # MODIFIED — middleware invalidates session on active suspension
│   ├── execution/
│   │   ├── service.py                             # MODIFIED — refuse new execution on cost cap; auto-terminate on time cap
│   │   └── scheduler.py                           # MODIFIED — wire cost-protection enforcement
│   ├── reasoning/
│   │   └── client.py                              # MODIFIED — pass max_reasoning_depth to gRPC; refuse over-depth
│   ├── common/
│   │   └── clients/
│   │       └── model_router.py                    # MODIFIED — refuse on plan-tier mismatch (Free vs premium model)
│   └── main.py                                    # MODIFIED — register cron + Kafka consumer in worker profile
├── tests/
│   ├── unit/security/abuse_prevention/            # NEW — ~12 unit tests
│   ├── integration/security/abuse_prevention/     # NEW — ~10 integration tests under integration_live mark
│   └── integration/migrations/
│       └── test_110_abuse_prevention.py           # NEW — migration smoke
└── pyproject.toml                                 # MODIFIED — add geoip2 dependency

apps/web/
├── app/(admin)/admin/security/
│   ├── abuse-prevention/page.tsx                  # NEW — overview + threshold tuning
│   ├── suspensions/
│   │   ├── page.tsx                               # NEW — review queue
│   │   └── [id]/page.tsx                          # NEW — suspension detail + lift
│   ├── email-overrides/page.tsx                   # NEW — disposable-email override list
│   └── geo-policy/page.tsx                        # NEW — geo-block configuration
├── components/features/admin/security/
│   ├── ThresholdEditor.tsx                        # NEW — per-knob editor (with live save)
│   ├── SuspensionQueueTable.tsx                   # NEW
│   ├── EvidencePanel.tsx                          # NEW — suspension evidence viewer
│   ├── DisposableEmailOverrideList.tsx            # NEW
│   ├── GeoPolicyEditor.tsx                        # NEW — deny/allow-list editor
│   └── RefusalReasonChart.tsx                     # NEW — Recharts time-series
└── lib/hooks/
    ├── use-abuse-prevention-settings.ts           # NEW — TanStack Query
    ├── use-suspensions.ts                         # NEW
    └── use-disposable-email-overrides.ts          # NEW

deploy/helm/
├── platform/values.yaml                           # MODIFIED — abuse_prevention block (geoip2_db_path, cron schedules)
└── observability/templates/dashboards/
    └── abuse-prevention.yaml                      # NEW — Grafana dashboard ConfigMap

docs/admin-guide/
└── abuse-prevention.md                            # NEW — operator walkthroughs

tests/e2e/suites/abuse_prevention/                 # NEW — J26 boundary scenarios
├── __init__.py
├── test_velocity_block.py
├── test_disposable_email.py
├── test_suspension_flow.py
├── test_free_tier_cost_protection.py
└── test_admin_overrides.py
```

**Structure Decision**: The new bounded context lives at `platform/security/abuse_prevention/` per the user input — a nested subpackage under a freshly created `security/` package (the existing `security_compliance/` BC stays unchanged). This is a deliberate divergence from the prior `100-upd-050-abuse` branch which used a flat `security_abuse/`. The nested layout leaves room for future security-related BCs (e.g., a hypothetical `security/incident_intake/`) without further restructuring.

Frontend follows the existing `app/(admin)/admin/*` pattern. No new app, no new package.

## Complexity Tracking

> *Fill ONLY if Constitution Check has violations that must be justified.*

No violations — Constitution Check passes. Section intentionally empty.
