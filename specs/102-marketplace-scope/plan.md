# Implementation Plan: UPD-049 — Marketplace Scope (Refresh Pass on 099 Baseline)

**Branch**: `102-marketplace-scope` | **Date**: 2026-05-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/102-marketplace-scope/spec.md`

## Summary

UPD-049 is already implemented in production as of 2026-05-03 by `specs/099-marketplace-scope/` (merged via PR #133). The agent profile carries `marketplace_scope`, `review_status`, `reviewed_at`, `reviewed_by_user_id`, `review_notes`, and `forked_from_agent_id` (Alembic 108). The `agents_visibility` RLS policy gates cross-tenant visibility on two GUCs (`app.tenant_kind`, `app.consume_public_marketplace`). The platform-staff review queue, the fork operation, and the per-tenant feature-flag toggle all work end-to-end at the service layer.

This **refresh pass** does NOT redo the data model or rewrite the migration. It closes the residual gaps the 099 NOTES.md documents and adds three new behavioural requirements that surfaced after merge:

1. **Self-review prevention** (FR-741.9) — the reviewer who approves/rejects a submission MUST NOT be the creator. Today `MarketplaceReviewService.approve` and `.reject` accept any `reviewer_id` and trust the caller; the gate must be enforced server-side at both the service layer and at the API layer.
2. **Information non-leakage parity** (FR-741.10 / SC-004) — when a tenant lacks the `consume_public_marketplace` flag, search-result counts, suggestion arrays, and analytics events MUST be byte-identical to a counter-factual in which the matching public-published agents do not exist. This is a stronger guarantee than the 099 RLS-only model; OpenSearch and ClickHouse paths need explicit visibility filtering audited end-to-end.
3. **Queue assignment distinct from claim** (FR-738, SC-007) — 099 implements a single-reviewer claim (the same column doubles as claim marker and final reviewer). Spec 102 calls out **assignment** as a separate concept: a platform-staff lead assigns a submission to a specific reviewer; the reviewer then claims and acts. Assignment vs. claim distinction lets one staff member balance the queue without taking ownership of every item.

In addition, the refresh closes the residual 099 follow-ups documented in `specs/099-marketplace-scope/NOTES.md`:

- **Live-DB integration fixture rollout** — 18 integration tests (T020 RLS cross-product, T023–T030, T048–T049, T054–T056, T060, T064–T069) committed under skipif markers naming the fixture they need. The refresh adds the fixture and removes the skip markers.
- **`MarketplaceFanoutConsumer` registration** — defined at `apps/control-plane/src/platform/marketplace/consumer.py:37` but not wired into any runtime profile lifespan. The refresh adds the one-line registration in the worker entrypoint.
- **Frontend integration** — T042 publish-page rewire, T058 listing-page badge, T059 admin tenants feature-flag toggle, T075 fork-button, T076 alert-renderer, T047/T050 Playwright E2E.
- **Fork quota integration** (T066) — `RegistryService.fork_agent` does not yet call the UPD-047 `quota_enforcer.check_agent_publish` because the fork target tenant's plan version isn't resolved on the fork path. The refresh resolves the consumer plan version and wires the check.
- **Tool-dependency cross-check** (T067) — fork response surfaces `mcp_server_refs` as `tool_dependencies_missing` instead of comparing against the consumer tenant's registered tools. The refresh implements the correct cross-tenant check.

The implementation remains **additive**. No table changes, no migrations, no new bounded contexts. The single new public-facing change is the assignment column on the agent profile (added via Alembic migration 109). Frontend follows existing `app/(admin)/admin/marketplace-review/*` and `components/features/marketplace/{publish,review}/` conventions.

## Technical Context

**Language/Version**: Python 3.12+ (control plane), TypeScript 5.x strict (Next.js admin + creator UI), SQL (Alembic Python migration targeting PostgreSQL 16)
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, Alembic 1.13+, aiokafka 0.11+, redis-py 5.x async, opensearch-py 2.x async, clickhouse-connect 0.8+, pytest + pytest-asyncio 8.x, ruff 0.7+, mypy 1.11+ strict; frontend uses existing Next.js 14+ App Router, React 18+, shadcn/ui (note: native `<select>` per CLAUDE.md, no Radix Select composite), Tailwind CSS 3.4+, TanStack Query v5, React Hook Form 7.x + Zod 3.x — all already in `apps/web/package.json`. **No new runtime packages.**
**Storage**: PostgreSQL — extends `registry_agent_profiles` via Alembic migration 109 with one new column (`assigned_reviewer_user_id UUID NULL`, FK `users.id ON DELETE SET NULL`), one new partial index (`assigned_reviewer_user_id` WHERE `review_status = 'pending_review'`), and one new audit-event entry kind. No new tables. No new GUCs (the existing `app.tenant_kind` and `app.consume_public_marketplace` cover all RLS branches). Redis — no new key families (the 099 `marketplace:submission_rate_limit:{user_id}` sliding-window key is unchanged); ClickHouse — read-only from the existing `usage_events` and `cost_events` tables for cost-attribution verification (SC-005); OpenSearch — visibility-filter audit on the existing `marketplace-agents` index (no schema change). MinIO/Qdrant/Neo4j unaffected.
**Testing**: pytest + pytest-asyncio for backend (unit / integration / RLS cross-product / migration smoke); Vitest + Playwright + axe-core for frontend; the integration-test live-DB+Kafka fixture introduced by this refresh follows the existing `tests/e2e/` pattern from feature 071.
**Target Platform**: Linux (Kubernetes via Helm chart); local dev via `make dev-up`
**Project Type**: Web service — Python control plane + Next.js admin/creator UI
**Performance Goals**: SC-001 — submission-to-approve median wall time observable and reportable (Grafana panel under existing marketplace dashboard); SC-006 — fork operation < 5 s p95 for a typical agent; SC-007 — review-queue listing < 2 s p95; SC-008 — rejection-reason notification delivered to submitter < 60 s p95.
**Constraints**: Self-review prevention (FR-741.9) MUST be enforced at both the service layer and the API layer (defense-in-depth); information non-leakage (FR-741.10) MUST be parity-tested at OpenSearch and ClickHouse paths in addition to PostgreSQL RLS; consume-flag toggle MUST invalidate the marketplace search cache (whatever its TTL); the audit chain hash MUST include the assignment-changed event with both the assigner and the assignee user IDs.
**Scale/Scope**: 1 new Alembic migration (109); 1 new column on `registry_agent_profiles`; 1 new partial index; ~3 new Pydantic schemas (`AssignReviewerRequest`, `ReviewerAssignmentResponse`, `MarketplaceParityProbeResult`); 4 new exception classes (`SelfReviewNotAllowedError`, `ReviewerAssignmentConflictError`, `PublicAgentNotFoundForConsumerError` for the 404-equivalent path, `MarketplaceParityViolationError` for the parity-test harness); 2 new Kafka event types on `marketplace.events` (`marketplace.review.assigned`, `marketplace.review.unassigned`) — additive to the 099 set; 3 new REST endpoints (`POST /api/v1/admin/marketplace-review/{agent_id}/assign`, `DELETE /api/v1/admin/marketplace-review/{agent_id}/assign`, `GET /api/v1/admin/marketplace-review/parity-probe?query={q}` — admin-only, dev-mode only behind the existing `FEATURE_E2E_MODE` flag for SC-004 verification); 5 frontend integration touchpoints (publish-page rewire, scope-badge on cards, fork-button gate, feature-flag toggle, source-updated alert renderer).

## Constitution Check

> *GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.3.0 governs UPD-023–UPD-045. UPD-049 is part of the SaaS Transformation Pass (UPD-046–UPD-054), post-audit-pass. The constitutional anchors that DO apply:

- **Brownfield rule 1 (never rewrite)**: ✅ all changes additive. Existing 099 service methods are extended, not replaced.
- **Brownfield rule 2 (every change is an Alembic migration)**: ✅ migration 109 (one column, one index).
- **Brownfield rule 3 (preserve all existing tests)**: ✅ no deletions; the skip markers on 099's scaffolded integration tests are removed once the live-DB fixture is in.
- **Brownfield rule 4 (use existing patterns)**: ✅ FastAPI router, Pydantic schemas, SQLAlchemy mixins, Kafka envelope, audit-chain service all reused.
- **Brownfield rule 5 (reference existing files)**: ✅ this plan and the contracts cite exact files at exact line numbers (e.g., `marketplace/review_service.py:147` for `claim`, `marketplace/consumer.py:37` for the unregistered consumer).
- **Brownfield rule 6 (additive enum values)**: ✅ no enum changes; the `assigned_reviewer_user_id` column is a UUID FK, not an enum.
- **Brownfield rule 7 (backward-compatible APIs)**: ✅ existing `claim`/`release`/`approve`/`reject` endpoints unchanged in signature; the new `assign`/`unassign` endpoints are additive; the publish endpoint's optional `scope` field continues to default to `workspace`.
- **Brownfield rule 8 (feature flags)**: ✅ the parity-probe endpoint is gated by `FEATURE_E2E_MODE` (existing); cross-tenant consumption remains gated by per-tenant `consume_public_marketplace`.
- **Rule 29 (admin endpoint segregation)**: ✅ assignment endpoints live under `/api/v1/admin/marketplace-review/*` (already established by 099).
- **Rule 30 (admin role gates)**: ✅ each new admin endpoint depends on `require_superadmin`.
- **Rule 34 (impersonation always double-audits)**: not in scope — this feature does not add impersonation; existing behaviour preserved.
- **Rule 36 (every new FR with UX impact must be documented)**: ✅ docs site (UPD-039 / spec 089) gets a section on "Marketplace Multi-Scope" reflecting the assignment workflow and the consume-flag opt-in path.
- **Rule 45 (every user-facing backend capability has a user-facing UI)**: ✅ all 5 frontend touchpoints listed in Scale/Scope.
- **Rule 47 (workspace-scoped vs platform-scoped distinction)**: ✅ the scope picker and the public-source label on cards visually distinguish scope; backend enforces it on every read path.
- **AD-20 (per-execution cost attribution)**: ✅ public-agent execution charged to the consumer tenant — already automatic via the existing cost-attribution path because `tenant_id` on the execution row is the consumer's; SC-005 verification is the new contribution here.

UPD-049 retains the three SaaS-pass-specific architectural decisions documented inline by 099:

- **SaaS hub-and-spoke** — Enterprise tenants may consume the public hub but never publish to it. Encoded in FR-733/734/741 (three-layer refusal preserved from 099).
- **Per-request RLS GUCs for cross-tenant visibility** — `app.tenant_id` (UPD-046), `app.tenant_kind`, `app.consume_public_marketplace`. Unchanged.
- **Single published-version invariant** — for any given agent profile, at most one row may have `review_status='published'`. Update flow re-enters review. Unchanged.

**Constitution Check verdict: PASS.** No violations to justify. Complexity Tracking section intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/102-marketplace-scope/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # /speckit-specify output
├── research.md          # Phase 0 — refresh-pass research decisions
├── data-model.md        # Phase 1 — single-column delta on registry_agent_profiles
├── quickstart.md        # Phase 1 — operator + reviewer-assigner walkthrough
├── contracts/           # Phase 1 — REST + Kafka contracts (delta to 099 contracts)
│   ├── reviewer-assignment-rest.md         # NEW — assign/unassign endpoints
│   ├── self-review-prevention.md           # NEW — service-layer + API guard contract
│   ├── non-leakage-parity-probe-rest.md    # NEW — dev-only parity probe endpoint
│   └── marketplace-events-kafka.md         # NEW — additive Kafka event types
├── checklists/
│   └── requirements.md  # Spec-quality checklist (created by /speckit-specify)
└── tasks.md             # /speckit-tasks output (NOT created by /speckit-plan)
```

### Source Code (repository root — modified or added by this refresh)

```text
apps/control-plane/
├── migrations/versions/
│   └── 109_marketplace_reviewer_assignment.py     # NEW — single column + partial index
├── src/platform/
│   ├── marketplace/
│   │   ├── admin_router.py                        # MODIFIED — add POST/DELETE assign endpoints + parity-probe (dev-only)
│   │   ├── review_service.py                      # MODIFIED — self-review guard in approve/reject; new assign/unassign methods
│   │   ├── consumer.py                            # MODIFIED — header docstring updated; module already exists
│   │   ├── notifications.py                       # MODIFIED — wire UPD-042 channel for rejection notifications (today uses inline notify shim)
│   │   ├── exceptions.py                          # MODIFIED — 4 new exception classes
│   │   ├── events.py                              # MODIFIED — 2 new Kafka event types
│   │   ├── search_service.py                      # MODIFIED — assert visibility filter applies BEFORE result-count emission for SC-004
│   │   └── parity_probe.py                        # NEW — dev-only parity-probe service backing the SC-004 test harness
│   ├── registry/
│   │   ├── models.py                              # MODIFIED — add assigned_reviewer_user_id column to AgentProfile
│   │   ├── service.py                             # MODIFIED — fork_agent: resolve consumer plan version + check_agent_publish (T066); compare mcp_server_refs against consumer tenant's tool registry (T067)
│   │   └── schemas.py                             # MODIFIED — add assigned_reviewer fields to ReviewQueueItem
│   └── analytics/
│       └── usage_consumer.py                      # MODIFIED — assert tenant_id on cost events is consumer tenant for public-agent invocations (SC-005 unit test)
├── tests/
│   ├── integration/marketplace/                   # MODIFIED — remove skip markers from 099's 18 scaffolded tests now that the live-DB+Kafka fixture is in
│   ├── integration/marketplace/test_self_review_prevention.py     # NEW
│   ├── integration/marketplace/test_assignment_lifecycle.py       # NEW
│   ├── integration/marketplace/test_non_leakage_parity.py         # NEW — search/count/suggestion/analytics parity
│   ├── integration/marketplace/test_cost_attribution_consumer.py  # NEW — SC-005
│   ├── integration/marketplace/test_consumer_registration.py      # NEW — MarketplaceFanoutConsumer wired in worker lifespan
│   └── unit/marketplace/test_self_review_guard.py                 # NEW
├── entrypoints/
│   └── worker_main.py                             # MODIFIED — register MarketplaceFanoutConsumer (one line)
└── conftest.py                                    # MODIFIED — register the live-DB+Kafka integration fixture (delegates to existing tests/e2e fixture from feature 071)

apps/web/
├── app/(admin)/admin/marketplace-review/
│   ├── page.tsx                                   # MODIFIED — assignment column, "unclaimed" / "assigned to me" / "assigned to others" filter chips
│   └── [agentId]/page.tsx                         # MODIFIED — Assign/Unassign action; self-review action gating
├── app/(admin)/admin/tenants/[id]/
│   └── feature-flags/page.tsx                     # NEW or MODIFIED — `consume_public_marketplace` toggle (T059)
├── app/(main)/agent-management/[fqn]/publish/
│   └── page.tsx                                   # MODIFIED — wire ScopePickerStep + MarketingMetadataForm (T042 follow-up)
├── app/(main)/marketplace/
│   ├── page.tsx                                   # MODIFIED — surface PublicSourceLabel on cards (T058)
│   └── [namespace]/[name]/page.tsx                # MODIFIED — wire ForkAgentDialog (T075)
├── components/features/marketplace/
│   ├── review/
│   │   ├── ReviewQueueAssignmentControls.tsx      # NEW
│   │   └── ReviewQueueFilterChips.tsx             # NEW
│   └── notifications/
│       └── SourceUpdatedAlertRenderer.tsx         # NEW (T076)
├── lib/marketplace/
│   └── notifications.ts                           # MODIFIED — alert-type → renderer map gains `marketplace.source_updated`
└── lib/hooks/
    ├── use-reviewer-assignment.ts                 # NEW — TanStack Query mutation hooks
    └── use-marketplace-review.ts                  # MODIFIED — surface assignment fields and filter state

deploy/helm/observability/templates/dashboards/
└── marketplace.yaml                               # MODIFIED — add SC-001/SC-007/SC-008 panels (submission-to-approve median, queue-listing p95, rejection-notification p95)

docs/saas/
└── marketplace-scope.md                           # MODIFIED — assignment section + consume-flag opt-in walkthrough (FR rule 36)
```

**Structure Decision**: Modular monolith pattern preserved. All work is additive to existing modules. The new `parity_probe.py` is a development-mode-only service guarded by the existing `FEATURE_E2E_MODE` flag — it is not a new bounded context. Frontend follows the existing `app/(admin)/admin/*` and `components/features/marketplace/*` conventions per CLAUDE.md (note: admin pages live under `(admin)/`, NOT `(main)/`, per the brownfield correction recorded in CLAUDE.md). No new app, no new package.

## Complexity Tracking

> *Fill ONLY if Constitution Check has violations that must be justified.*

No violations — Constitution Check passes. Section intentionally empty.
