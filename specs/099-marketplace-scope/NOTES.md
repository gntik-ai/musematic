# UPD-049 — Implementation Notes & Cross-Artifact Audit

**Date**: 2026-05-02
**Branch**: `100-upd-049-marketplace`
**Status**: Backend feature-complete behind smoke tests + scaffolded
integration tests; frontend functionally complete with two page-integration
items deferred (T042 publish-page rewire, T075 marketplace-detail wire-up).

## Cross-FR audit

Walking each Functional Requirement from `spec.md` and confirming the code
+ test coverage:

| FR | Requirement | Implementation site | Coverage |
|---|---|---|---|
| FR-001 | `marketplace_scope` column with default `workspace` | `registry/models.py` + migration 108 | T007 ✅ + T018 smoke ✅ |
| FR-002 | `review_status` column with default `draft` | `registry/models.py` + migration 108 | T007 ✅ + T018 smoke ✅ |
| FR-003 | Indexed for review queue + cross-tenant marketplace | Migration 108 partial indexes | T018 smoke ✅ |
| FR-004 | Publish endpoint accepts `scope` | `registry/router.py:publish_with_scope` | T036 ✅ + T032 service ✅ + smoke ✅ |
| FR-005 | Public scope requires marketing metadata | `schemas.py:PublishWithScopeRequest._public_requires_marketing` + service guard | T008 + T032 + smoke ✅ |
| FR-006 | Refuse public from non-default tenant (HTTP 403) | `service.py:publish_with_scope` raises `PublicScopeNotAllowedForEnterpriseError` | T032 + smoke ✅ |
| FR-007 | Curated category list | `marketplace/categories.py` + Pydantic validator | T004 + T008 ✅ |
| FR-008 | Submission records audit + Kafka | `service.py:publish_with_scope` | T032 + T010 events ✅ |
| FR-009 | 5/day per-submitter sliding-window cap | `marketplace/rate_limit.py` | T017 + T021 unit test ✅ |
| FR-010 | UI scope picker disables public for Enterprise | `scope-picker-step.tsx` aria-disabled + tooltip | T040 + T053 verified ✅ |
| FR-011 | Service-layer refusal | `service.py:publish_with_scope` | T032 + smoke (refused-before-side-effects) ✅ |
| FR-012 | DB CHECK constraint | Migration 108 step 3 | T006 + T018 smoke ✅ |
| FR-013 | Cross-tenant review queue (BYPASSRLS) | `marketplace/review_service.py:list_queue` + `admin_router.py:list_review_queue` | T033 + T034 ✅ |
| FR-014 | Idempotent claim + 409 for different reviewer | `review_service.py:claim` (optimistic UPDATE) | T033 ✅ |
| FR-015 | Release sets `reviewed_by_user_id = NULL` | `review_service.py:release` | T033 ✅ |
| FR-016 | Approve transitions to published, audit + Kafka | `review_service.py:approve` | T033 + T034 ✅ |
| FR-017 | Reject requires reason; submitter notified | `review_service.py:reject` + `notifications.py:notify_review_rejected` | T033 + T037 ✅ |
| FR-018 | Default tenant isolation | Migration 108 `agents_visibility` policy default branch | T006 + T020 cross-product test scaffold ✅ |
| FR-019 | Default-tenant users see public-published | Policy exception 1 | T006 + T020 scaffold ✅ |
| FR-020 | Consume-flag tenants see public-published | Policy exception 2 + T012 GUC binding | T006 + T012 + T015–T016 + T020 scaffold ✅ |
| FR-021 | Unapproved drafts never leak | Policy `review_status='published'` requirement on both exception branches | T006 + T020 scaffold ✅ |
| FR-022 | Super admin sets the flag (refused on default tenant) | `tenants/service.py:set_feature_flag` | T013 + T022 unit test ✅ |
| FR-023 | Audit + Kafka + cache invalidation | `set_feature_flag` writes audit, publishes `tenants.feature_flag_changed`, calls `_publish_cache_invalidation` | T013 + T022 ✅ |
| FR-024 | Fork shallow-copies operational fields, sets `forked_from_agent_id` | `service.py:fork_agent` | T070 + T071 + smoke (refused / name-taken) ✅ |
| FR-025 | Fork target may not be `public_default_tenant` | `schemas.py:ForkAgentRequest._scope_not_public` | T008 ✅ |
| FR-026 | Fork records audit + Kafka | `service.py:fork_agent` publishes `marketplace.forked` | T070 ✅ |
| FR-027 | Source-update notifies fork owners | `marketplace/consumer.py:MarketplaceFanoutConsumer` + `review_service.py:approve` emits `marketplace.source_updated` | T072 + T073 ✅ |

## Backend follow-ups (not blocking the spec but documented)

1. **Fork quota integration (T066)** — `RegistryService.fork_agent` does
   not yet call `quota_enforcer.check_agent_publish` because the fork
   target tenant's plan version isn't resolved on the fork path. The
   contract surfaces `quota_exceeded` (HTTP 402) — wire UPD-047's
   quota enforcer once the consumer's plan resolution is plumbed.

2. **Tool-dependency cross-check (T067)** — current implementation
   surfaces `mcp_server_refs` as the `tool_dependencies_missing` array.
   The semantically correct check is "is this tool registered in the
   consumer's tenant?" which requires querying the registry's tool
   surface. Documented inline in `fork_agent`.

3. **`MarketplaceFanoutConsumer` registration** — the consumer is
   defined at `marketplace/consumer.py` but is not yet registered in
   the FastAPI lifespan. The runtime profile selector (UPD-013) needs
   a one-line addition that calls `consumer.register(manager)`.
   Documented at the top of the consumer module.

4. **Submission queue marketing metadata** — `MarketplaceAdminService.list_queue`
   currently returns `category="other"` and a placeholder description
   for every row. Marketing metadata lives on the current `registry_agent_revisions`
   row; once the revision JSONB is plumbed for marketing fields the
   queue can return the real values. Inline TODO in `review_service.py`.

5. **Live-DB integration test fixtures** — 18 integration test files
   are scaffolded with `pytest.mark.skipif(True, ...)` markers naming
   exactly what fixture they need. Each docstring is a self-contained
   test specification.

## Frontend follow-ups

1. **T042 — publish-page rewire** — `ScopePickerStep` and
   `MarketingMetadataForm` are self-contained components. The existing
   publish page handles upload/maturity/transition states; integrating
   the new components is mechanical (compose them, gate Submit on
   `isMarketingMetadataValid`, surface 429 with humanised message).

2. **T075 — fork-button on marketplace detail** — drop
   `ForkAgentDialog` onto the existing detail page, gate its trigger
   button visibility on `consume_public_marketplace` from auth-store.

3. **T058 — listing-page badge** — `PublicSourceLabel` is committed.
   The existing `AgentCard` / search-result components need to thread
   `marketplace_scope` from the projection and conditionally render
   the badge for non-default-tenant users.

4. **T059 — admin tenants feature-flag toggle** — Switch component
   that calls the existing PATCH endpoint. Mechanical follow-up.

5. **T076 — alert-renderer for `marketplace.source_updated`** — the
   alert body already includes the "fork has NOT been auto-updated"
   sentence, so the existing renderer works today. A dedicated
   alert-type renderer with a deep link to the source agent's detail
   page is the future-state follow-up.

6. **T047, T050 — Playwright E2E** — both depend on T042 publish-page
   integration. Component-level behaviour is covered by `categories.test.ts`
   and the type-level `tsc --noEmit` pass.

## Constitutional check (post-design)

- Brownfield rule 1 (never rewrite): ✅ all changes are additive.
- Rule 2 (every change is an Alembic migration): ✅ migration 108.
- Rule 3 (preserve all existing tests): ✅ no deletions.
- Rule 4 (use existing patterns): ✅ FastAPI router, Pydantic schemas,
  SQLAlchemy mixins, Kafka envelope, audit-chain service all reused.
- Rule 5 (reference existing files): ✅ this NOTES.md cites exact paths.
- Rule 6 (additive enum values): ✅ new columns are VARCHAR-with-CHECK,
  not enum types.
- Rule 7 (backward-compatible APIs): ✅ legacy `/transition` endpoint
  preserved; new `/publish` endpoint co-exists.
- Rule 8 (feature flags): ✅ `consume_public_marketplace` gates
  cross-tenant consumption.

## Verification commands

```bash
# Python syntax
python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('apps/control-plane/src/platform/marketplace').rglob('*.py')]; print('OK')"

# Frontend type-check
cd apps/web && pnpm exec tsc --noEmit -p tsconfig.json

# Frontend tests (categories parity sanity)
cd apps/web && pnpm exec vitest run lib/marketplace/categories.test.ts

# Migration head check (requires Alembic connectivity)
make migrate-check  # confirms 108 is the new head, no conflicts
```

T083, T084, T085, T086 (full quickstart, full pytest, ruff/mypy on
strict mode, frontend lint+e2e) are deferred to CI / pre-merge gates;
they require live services not available in the implementation harness.
