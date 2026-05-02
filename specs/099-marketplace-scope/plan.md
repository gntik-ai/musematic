# Implementation Plan: UPD-049 — Marketplace Scope

**Branch**: `100-upd-049-marketplace` | **Date**: 2026-05-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/099-marketplace-scope/spec.md`

## Summary

UPD-049 adds the marketplace scope dimension (`workspace` / `tenant` /
`public_default_tenant`), the platform-staff review queue for public submissions, the
fork operation, and the per-Enterprise-tenant `consume_public_marketplace` feature flag.

The implementation is **additive** to the existing registry bounded context
(`apps/control-plane/src/platform/registry/`) and reuses the multi-tenant RLS scaffolding
introduced by UPD-046. A single Alembic migration (108) extends the
`registry_agent_profiles` table with six columns, two partial indexes, three CHECK
constraints, and replaces the `tenant_isolation` policy (created by migration 100) with a
new `agents_visibility` policy that keeps tenant isolation as the default branch but adds
two narrow exceptions for cross-tenant visibility of public-published rows.

A new `apps/control-plane/src/platform/marketplace/admin_router.py` skeleton mounts under
the existing composite admin router and serves the platform-staff review-queue endpoints.
A new shared module `apps/control-plane/src/platform/marketplace/categories.py` holds the
platform-curated category list. A new `apps/control-plane/src/platform/marketplace/rate_limit.py`
implements the 5/day-per-submitter sliding window via a Redis sorted set.

The frontend (`apps/web/`) gains a scope picker step inside the existing publish flow, a
new `/admin/marketplace-review` route group with queue and detail pages, and a fork
dialog on the marketplace agent detail page.

The three-layer Enterprise refusal (UI scope-picker disable + service guard + database
CHECK constraint) is the security backbone of the feature and is mandatory per FR-010,
FR-011, FR-012.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js admin
+ creator UI), SQL (Alembic Python migrations targeting PostgreSQL 16)
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic
1.13+, aiokafka 0.11+, redis-py 5.x async, pytest + pytest-asyncio 8.x, ruff 0.7+, mypy
1.11+ strict; frontend uses existing Next.js 14+ App Router, React 18+, shadcn/ui,
Tailwind CSS 3.4+, TanStack Query v5, React Hook Form 7.x + Zod 3.x — all already in
`apps/web/package.json`. **No new runtime packages.**
**Storage**: PostgreSQL — extends `registry_agent_profiles` via Alembic migration 108
(no new tables); Redis — one new key family
`marketplace:submission_rate_limit:{user_id}` (sliding-window sorted set, 24h
window-length TTL); no new MinIO / Qdrant / Neo4j / ClickHouse / OpenSearch surfaces.
**Testing**: pytest + pytest-asyncio for backend (unit / integration / migration smoke);
Vitest + Playwright for frontend
**Target Platform**: Linux (Kubernetes via Helm chart); local dev via `make dev-up`
**Project Type**: Web service — Python control plane + Next.js admin/creator UI
**Performance Goals**: SC-005 — public-marketplace search first page p95 < 1.5 s on
representative dataset; SC-006 — fork operation < 5 s for a typical agent
**Constraints**: Defense-in-depth Enterprise refusal at UI + service + DB layers
(FR-010/011/012); RLS policy never permits cross-tenant visibility of unapproved rows
(FR-021); rate limiter must not block on Redis outages (fail-closed for safety); audit
chain hash includes `tenant_id` per UPD-046 R7
**Scale/Scope**: ~5 new Pydantic schemas, ~10 new exception classes, 8 new Kafka event
types on `marketplace.events` topic + 1 new event on `tenants.lifecycle`, 1 new Alembic
migration, ~6 new REST endpoints (publish-with-scope extension + 5 admin review queue
endpoints + 1 fork endpoint + 2 marketplace-scope-change/deprecate-listing endpoints)

## Constitution Check

> *GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.3.0 (Sync Impact Report at top of `.specify/memory/constitution.md`)
governs the audit-pass scope (UPD-023 through UPD-045). UPD-049 is part of the SaaS
Transformation Pass (UPD-046–UPD-054), which is post-audit-pass. The relevant
constitutional anchors that DO apply:

- **Brownfield rule 1 (never rewrite)**: ✅ all changes are additive to
  `registry_agent_profiles`, `registry/service.py`, `registry/router.py`, etc.
- **Brownfield rule 2 (every change is an Alembic migration)**: ✅ migration 108.
- **Brownfield rule 3 (preserve all existing tests)**: ✅ no existing test deletions; new
  tests added under `tests/integration/marketplace/` and `tests/unit/marketplace/`.
- **Brownfield rule 4 (use existing patterns)**: ✅ FastAPI router, Pydantic schemas,
  SQLAlchemy mixins, Kafka envelope, and audit-chain service all reused as-is.
- **Brownfield rule 5 (reference existing files)**: ✅ this plan and the contracts cite
  exact files.
- **Brownfield rule 6 (additive enum values)**: ✅ no enum-value changes — `marketplace_scope`
  and `review_status` are new VARCHAR-with-CHECK columns.
- **Brownfield rule 7 (backward-compatible APIs)**: ✅ the publish endpoint gains an
  optional `scope` field (defaults to `workspace`, today's behaviour).
- **Brownfield rule 8 (feature flags)**: ✅ public consumption gated by the
  `consume_public_marketplace` per-tenant flag introduced in this feature.
- **AD-20 (per-execution cost attribution)**: ✅ public-agent execution charged to the
  consumer tenant — already automatic via the existing cost-attribution path because
  `tenant_id` on the execution row is the consumer's tenant.

UPD-049 also adds three SaaS-pass-specific architectural decisions documented inline
(spec Assumptions + plan Phase 0 research) since the SaaS-pass constitution amendment is
out of scope for this feature:

- **SaaS hub-and-spoke** — Enterprise tenants may consume the public hub but never
  publish to it. Encoded in FR-010/011/012 (three-layer refusal).
- **Per-request RLS GUCs for cross-tenant visibility** — `app.tenant_id` (existing,
  UPD-046), `app.tenant_kind`, and `app.consume_public_marketplace`. Encoded in
  research R3 + the migration's policy expression.
- **Single published-version invariant** — for any given agent profile, at most one row
  may have `review_status='published'`. Update flow re-enters review.

**Constitution Check verdict: PASS.** No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/099-marketplace-scope/
├── plan.md              # This file (/speckit.plan output)
├── spec.md              # /speckit.specify output
├── research.md          # Phase 0 — research decisions
├── data-model.md        # Phase 1 — extends registry_agent_profiles, no new tables
├── quickstart.md        # Phase 1 — operator + creator + reviewer walkthroughs
├── contracts/           # Phase 1 — REST + Kafka contracts
│   ├── publish-and-review-rest.md
│   ├── admin-marketplace-review-rest.md
│   ├── consume-flag-rest.md
│   ├── fork-rest.md
│   └── marketplace-events-kafka.md
├── checklists/
│   └── requirements.md  # Spec-quality checklist (created by /speckit.specify)
└── tasks.md             # /speckit.tasks output (NOT created by /speckit.plan)
```

### Source Code (repository root — modified or added by this feature)

```text
apps/control-plane/
├── migrations/versions/
│   └── 108_marketplace_scope_and_review.py          # NEW (single migration)
├── src/platform/
│   ├── common/
│   │   ├── config.py                                # MODIFIED — add MARKETPLACE_* settings
│   │   ├── database.py                              # MODIFIED — extend before_cursor_execute listener
│   │   └── tenant_context.py                        # MODIFIED — add consume_public_marketplace field
│   ├── marketplace/
│   │   ├── admin_router.py                          # NEW — review-queue endpoints
│   │   ├── categories.py                            # NEW — MARKETING_CATEGORIES tuple
│   │   ├── rate_limit.py                            # NEW — Redis sliding-window per submitter
│   │   ├── review_service.py                        # NEW — claim/release/approve/reject
│   │   ├── notifications.py                         # NEW — rejection + source-updated fan-out helpers
│   │   └── service.py                               # MODIFIED — extend with scope handling
│   ├── registry/
│   │   ├── events.py                                # MODIFIED — 8 new marketplace event types
│   │   ├── exceptions.py                            # MODIFIED — 10 new exception classes
│   │   ├── models.py                                # MODIFIED — 6 new columns on AgentProfile
│   │   ├── router.py                                # MODIFIED — publish-scope, marketplace-scope, deprecate-listing, fork
│   │   ├── schemas.py                               # MODIFIED — 8 new schemas
│   │   ├── service.py                               # MODIFIED — publish_with_scope, fork_agent
│   │   └── state_machine.py                        # MODIFIED — review_status transitions
│   └── tenants/
│       ├── admin_router.py                          # MODIFIED — feature_flags surface on PATCH /tenants/{id}
│       ├── events.py                                # MODIFIED — tenants.feature_flag_changed
│       ├── resolver.py                              # MODIFIED — expose consume_public_marketplace
│       └── service.py                               # MODIFIED — set_feature_flag method
└── tests/
    ├── integration/marketplace/                     # NEW — 11 integration tests
    ├── unit/marketplace/                            # NEW — 4 unit tests
    └── unit/tenants/                                # MODIFIED — add set_feature_flag test

apps/web/
├── app/(main)/admin/marketplace-review/
│   ├── page.tsx                                     # NEW — review queue
│   └── [agentId]/page.tsx                           # NEW — submission detail
├── app/(main)/agent-management/[fqn]/publish/
│   └── page.tsx                                     # MODIFIED — scope picker step
├── app/(main)/marketplace/
│   ├── page.tsx                                     # MODIFIED — public-scope filter + label
│   └── [namespace]/[name]/page.tsx                  # MODIFIED — fork dialog
├── components/features/marketplace/
│   ├── ScopePickerStep.tsx                          # NEW
│   ├── MarketingMetadataForm.tsx                    # NEW
│   ├── ReviewQueueTable.tsx                         # NEW
│   ├── ReviewSubmissionDetail.tsx                   # NEW
│   ├── ForkAgentDialog.tsx                          # NEW
│   └── PublicSourceLabel.tsx                        # NEW
├── lib/marketplace/
│   ├── categories.ts                                # NEW — mirror of backend categories
│   └── types.ts                                     # NEW — mirror Pydantic schemas
└── lib/hooks/
    ├── use-marketplace-review.ts                    # NEW — TanStack Query hooks for queue
    └── use-publish-with-scope.ts                    # NEW — publish mutation with scope payload

deploy/helm/platform/
├── values.yaml                                      # MODIFIED — marketplace block
├── values.dev.yaml                                  # MODIFIED — mirror
└── values.prod.yaml                                 # MODIFIED — mirror
```

**Structure Decision**: Modular monolith pattern preserved. The new
`platform/marketplace/` directory holds review-queue + rate-limit + notification helpers
(not a new bounded context — it's a thin admin surface that delegates persistence to the
existing `registry/` bounded context). Frontend follows the existing
`app/(main)/admin/*` and `components/features/marketplace/*` conventions. No new app, no
new package.

## Complexity Tracking

> *Fill ONLY if Constitution Check has violations that must be justified.*

No violations — Constitution Check passes. Section intentionally empty.
