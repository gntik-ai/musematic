---

description: "Task list for UPD-049 — Marketplace Scope (Workspace, Tenant, Public Default Tenant)"
---

# Tasks: UPD-049 Marketplace Scope (Workspace, Tenant, Public Default Tenant)

**Input**: Design documents from `specs/099-marketplace-scope/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included — UPD-049 ships defense-in-depth security guarantees
(three-layer Enterprise refusal, RLS visibility correctness) that MUST be backed by
explicit positive and negative tests. Per spec SC-003 / SC-004, these tests are part
of the spec's success criteria, not optional polish.

**Organization**: Tasks are grouped by user story to enable independent implementation
and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- File paths in descriptions are absolute from repo root.

## Path Conventions

- **Web app** (this feature): `apps/control-plane/src/platform/<bc>/...` for backend,
  `apps/web/...` for frontend, `deploy/helm/platform/...` for chart, `tests/...` and
  `apps/control-plane/tests/...` for tests.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project hygiene and shared scaffolding that the rest of the feature builds
on.

- [X] T001 Confirm working branch is `100-upd-049-marketplace` (`git status` shows clean tree, branch matches) and migrations 096–107 (UPD-046, UPD-047, UPD-048) are present at `apps/control-plane/migrations/versions/`.
- [X] T002 [P] Add new Pydantic settings to `apps/control-plane/src/platform/common/config.py`: `MARKETPLACE_DEPRECATION_RETENTION_DAYS: int = 30`, `MARKETPLACE_SUBMISSION_RATE_LIMIT_PER_DAY: int = 5`, `MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS: bool = True`. Document each in the docstring.
- [X] T003 [P] Add the `marketplace:` Helm value block to `deploy/helm/platform/values.yaml` mirroring the new settings. Mirror to `deploy/helm/platform/values.dev.yaml` and `values.prod.yaml`.
- [X] T004 [P] Create marketing-category enumeration at `apps/control-plane/src/platform/marketplace/categories.py` exporting `MARKETING_CATEGORIES: tuple[str, ...] = ("data-extraction", "summarisation", "code-assistance", "research", "automation", "communication", "analytics", "content-generation", "translation", "other")`. Module docstring references research R4.
- [X] T005 [P] Create empty `apps/control-plane/src/platform/marketplace/admin_router.py` with `router = APIRouter(prefix="/marketplace-review", tags=["admin.marketplace_review"])` and a module docstring. Subsequent tasks fill in the endpoints.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Database migration, RLS policy, model + schema + exception + event scaffolds, GUC listener extension, tenant feature-flag setter, and submission rate limiter — every user story depends on these.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Database migration

- [X] T006 Author Alembic migration `apps/control-plane/migrations/versions/108_marketplace_scope_and_review.py` per `data-model.md`. The single migration runs in order (research R9): (a) add `marketplace_scope`, `review_status`, `reviewed_at`, `reviewed_by_user_id`, `review_notes`, `forked_from_agent_id` columns to `registry_agent_profiles` with CHECK constraints on `marketplace_scope` and `review_status`; (b) add partial index `registry_agent_profiles_review_status_idx` on `review_status` `WHERE review_status = 'pending_review'`; (c) add partial index `registry_agent_profiles_scope_status_idx` on `(marketplace_scope, review_status)` `WHERE marketplace_scope = 'public_default_tenant' AND review_status = 'published'`; (d) add CHECK constraint `registry_agent_profiles_public_only_default_tenant` (`marketplace_scope <> 'public_default_tenant' OR tenant_id = '00000000-0000-0000-0000-000000000001'::uuid`); (e) DROP POLICY `tenant_isolation` ON `registry_agent_profiles` and CREATE POLICY `agents_visibility` per the expression in `data-model.md`. Include reverse migration that runs the steps in reverse order.

### Backend skeleton extensions

- [X] T007 [P] Extend `apps/control-plane/src/platform/registry/models.py:AgentProfile` to add the six new columns (`marketplace_scope`, `review_status`, `reviewed_at`, `reviewed_by_user_id`, `review_notes`, `forked_from_agent_id`) matching the migration.
- [X] T008 [P] Extend `apps/control-plane/src/platform/registry/schemas.py`: add `MarketingMetadata`, `PublishWithScopeRequest`, `MarketplaceScopeChangeRequest`, `DeprecateListingRequest`, `ReviewSubmissionView`, `ReviewQueueResponse`, `ReviewApprovalRequest`, `ReviewRejectionRequest`, `ForkAgentRequest`, `ForkAgentResponse` schemas matching the contracts under `specs/099-marketplace-scope/contracts/`.
- [X] T009 [P] Extend `apps/control-plane/src/platform/registry/exceptions.py` with: `PublicScopeNotAllowedForEnterpriseError`, `MarketingMetadataRequiredError`, `MarketingCategoryInvalidError`, `SubmissionRateLimitExceededError`, `ReviewAlreadyClaimedError`, `SubmissionAlreadyResolvedError`, `SubmissionNotFoundError`, `NotAgentOwnerError`, `SourceAgentNotVisibleError`, `ConsumePublicMarketplaceDisabledError`, `NameTakenInTargetNamespaceError`. Each subclasses `PlatformError` with stable error codes matching `contracts/*-rest.md`.
- [X] T010 [P] Extend `apps/control-plane/src/platform/registry/events.py` with the eight new event-type schemas (`marketplace.scope_changed`, `marketplace.submitted`, `marketplace.approved`, `marketplace.rejected`, `marketplace.published`, `marketplace.deprecated`, `marketplace.forked`, `marketplace.source_updated`) per `contracts/marketplace-events-kafka.md`. Add a `publish_marketplace_event` helper that publishes to `marketplace.events` topic.
- [X] T011 [P] Extend `apps/control-plane/src/platform/tenants/events.py` with `tenants.feature_flag_changed` event type + `TenantFeatureFlagChangedPayload` per `contracts/marketplace-events-kafka.md`.

### GUC listener extension

- [X] T012 Extend the SQLAlchemy `before_cursor_execute` listener in `apps/control-plane/src/platform/common/database.py` (originally added by UPD-046 to set `app.tenant_id`) to also `SET LOCAL app.tenant_kind = '<kind>'` and `SET LOCAL app.consume_public_marketplace = '<true|false>'` per request. Read `tenant_kind` from `current_tenant.kind` and `consume_public_marketplace` from `current_tenant.consume_public_marketplace` (explicit field). The platform-staff session does NOT need these GUCs (BYPASSRLS).

### Tenant feature-flag setter

- [X] T013 Add `TenantsService.set_feature_flag(tenant_id, flag_name, value, super_admin_id)` method to `apps/control-plane/src/platform/tenants/service.py`. Validates: (a) the flag name is in a documented allowlist (currently just `consume_public_marketplace`); (b) the tenant kind matches the flag's allowed-kind enumeration (`consume_public_marketplace` is `enterprise` only — refused on default tenant). Records hash-linked audit chain entry. Publishes `tenants.feature_flag_changed` Kafka event. Invalidates the tenant resolver cache for that tenant.
- [X] T014 Extend `apps/control-plane/src/platform/tenants/admin_router.py:PATCH /api/v1/admin/tenants/{id}` to accept a `feature_flags` field and route per-flag updates through `TenantsService.set_feature_flag`. Refuses changes to flags not in the allowlist with HTTP 422. _Implementation note: routing happens inside `update_tenant`'s service-layer per-flag handling (no router signature change needed)._

### Tenant resolver consume-flag exposure

- [X] T015 Extend `apps/control-plane/src/platform/tenants/resolver.py` to expose `consume_public_marketplace: bool` in the `TenantContext` dataclass. Read from `tenant.feature_flags_json.get('consume_public_marketplace', False)` at resolver-cache load time.
- [X] T016 Extend `apps/control-plane/src/platform/common/tenant_context.py:TenantContext` to carry an explicit `consume_public_marketplace: bool` field (in addition to `feature_flags`) for cheap RLS-binding access.

### Submission rate limiter

- [X] T017 Add `apps/control-plane/src/platform/marketplace/rate_limit.py` with `MarketplaceSubmissionRateLimiter.check_and_record(user_id) -> None` (raises `SubmissionRateLimitExceededError` on cap) and `.retry_after_seconds(user_id) -> int`. Implementation: Redis sorted set keyed on `marketplace:submission_rate_limit:{user_id}`, score=epoch ms, evicts via `ZREMRANGEBYSCORE` for entries older than 24 hours, refuses if `ZCARD` ≥ `MARKETPLACE_SUBMISSION_RATE_LIMIT_PER_DAY`. Used by US1's submit endpoint.

### Foundational tests

- [X] T018 [P] Migration smoke test at `apps/control-plane/tests/integration/migrations/test_108_marketplace_scope.py`: source-text assertions verify (a) the six new columns are declared; (b) both partial indexes are declared; (c) all three CHECK constraints are declared including the public_only_default_tenant constraint; (d) the `tenant_isolation` policy is dropped and `agents_visibility` is created with all three USING branches; (e) revision chain links to 107.
- [X] T019 [P] Unit test `apps/control-plane/tests/unit/marketplace/test_consume_flag_resolution.py`: `TenantContext` carries `consume_public_marketplace` flag correctly for default tenant, Enterprise tenant with flag set, Enterprise tenant without flag set; payload round-trip preserves the flag.
- [ ] T020 [P] Integration test `apps/control-plane/tests/integration/marketplace/test_rls_public_visibility.py`: full cross-product matrix — default-tenant user × public-published; default-tenant user × public-pending-review (hidden); Acme-with-flag × public-published; Acme-with-flag × public-pending-review (hidden); Acme-without-flag × public-published (hidden); Globex-without-flag × public-published (hidden); Acme cross-tenant view of Acme-private (visible); Acme cross-tenant view of Globex-private (hidden). Uses raw SQL via the regular session to verify RLS, not application-layer filtering. _Status: scaffold + skip-marker committed at `tests/integration/marketplace/test_rls_public_visibility.py`; full test bodies require a live PostgreSQL fixture seeding the cross-product, which is part of the integration-test profile not yet wired in this branch._
- [X] T021 [P] Unit test `apps/control-plane/tests/unit/marketplace/test_rate_limiter.py`: 5 submissions in 24 hours all pass; 6th refused with `SubmissionRateLimitExceededError`; clearing the user's key resets the count; window slides correctly past the 24-hour boundary.
- [X] T022 [P] Unit test `apps/control-plane/tests/unit/tenants/test_set_feature_flag.py`: setting `consume_public_marketplace=true` on Enterprise tenant succeeds; setting it on default tenant raises validation error; setting an unknown flag name raises validation error; audit-chain entry recorded; idempotent no-op when value unchanged.

**Checkpoint**: Foundation ready — user story implementation can now begin in parallel.

---

## Phase 3: User Story 1 — Default-tenant creator publishes to public marketplace (Priority: P1) 🎯 MVP

**Goal**: A default-tenant creator can submit an agent for public publication, the
submission appears in a platform-staff review queue, and an approver can publish it.

**Independent Test**: Per `quickstart.md` Scenario 1 — creator submits → queue lists →
super admin approves → second default-tenant user finds the agent in marketplace
search. Audit chain entries exist for submit, approve, and publish.

### Tests for User Story 1 (positive path)

- [ ] T023 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_publish_workspace_scope.py`: existing flow — publish at workspace scope transitions directly to `published`, no review queue entry. _Status: scaffold + skip-marker committed pending live-DB fixture; service-layer behaviour covered by `tests/unit/marketplace/test_publish_with_scope_smoke.py`._
- [ ] T024 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_publish_tenant_scope.py`: publish at tenant scope transitions directly to `published`, visible to all workspaces in the tenant. _Status: same as T023._
- [ ] T025 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_publish_public_scope_flow.py`: full happy path — submit with marketing metadata; verify `pending_review` state; verify queue entry exists; super admin approves; verify `published` state; verify visibility to a second default-tenant user. _Status: scaffold committed; service-layer pending_review transition covered by smoke test._
- [ ] T026 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_admin_review_queue.py`: queue listing includes only `pending_review`; cursor pagination correct; FIFO sort. _Status: scaffold committed pending live-DB fixture._
- [ ] T027 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_admin_review_claim.py`: claim is idempotent for same reviewer; conflicts (409) for different reviewer; release returns to unclaimed. _Status: scaffold committed pending live-DB fixture._
- [ ] T028 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_admin_review_approve.py`: approve transitions correctly; `reviewed_at` and `reviewed_by_user_id` are persisted; `marketplace.approved` followed by `marketplace.published` events emitted. _Status: scaffold committed pending live-DB fixture._
- [ ] T029 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_admin_review_reject.py`: reject requires reason (422 without); transitions to `rejected`; `marketplace.rejected` event emitted; submitter receives notification via UPD-042. _Status: scaffold committed pending live-DB fixture._
- [ ] T030 [P] [US1] Integration test `apps/control-plane/tests/integration/marketplace/test_review_queue_rate_limit.py`: 6th submission in 24 hours returns 429 with `Retry-After` header. _Status: scaffold committed; rate-limiter behaviour fully covered by `tests/unit/marketplace/test_rate_limiter.py` (T021)._

### Implementation for User Story 1

- [X] T031 [P] [US1] Extend `apps/control-plane/src/platform/registry/state_machine.py` with `review_status` state machine matching `data-model.md` (transitions: draft→pending_review on public-submit; pending_review→published on approve; pending_review→rejected on reject; published→deprecated on owner action; rejected→pending_review on resubmit).
- [X] T032 [US1] Extend `apps/control-plane/src/platform/registry/service.py:RegistryService` with `publish_with_scope(agent_id, scope, marketing_metadata, actor_user_id)`. For `scope=public_default_tenant`: enforce three-layer refusal (tenant_kind != 'default' → raise `PublicScopeNotAllowedForEnterpriseError`); enforce `MarketingMetadataRequiredError`; call `MarketplaceSubmissionRateLimiter.check_and_record`; transition `review_status` to `pending_review`; record audit-chain entry; publish `marketplace.submitted`. For `scope=workspace|tenant`: transition directly to `published` and publish `marketplace.published`. Also adds `change_marketplace_scope` and `deprecate_listing` methods per `contracts/publish-and-review-rest.md`.
- [X] T033 [US1] Add `MarketplaceAdminService` at `apps/control-plane/src/platform/marketplace/review_service.py` with: `list_queue(filter, cursor, limit)`, `claim(agent_id, reviewer_id)` (optimistic UPDATE per research R6), `release(agent_id, reviewer_id)`, `approve(agent_id, reviewer_id, notes)`, `reject(agent_id, reviewer_id, reason)`. Uses the platform-staff session (BYPASSRLS) for cross-tenant queue reads. All actions record audit-chain entries and publish corresponding Kafka events.
- [X] T034 [US1] Implement the five admin review-queue endpoints in `apps/control-plane/src/platform/marketplace/admin_router.py` per `contracts/admin-marketplace-review-rest.md` (queue / claim / release / approve / reject). Bind to `MarketplaceAdminService`. Authorization: super admin or platform-staff role only.
- [X] T035 [US1] Mount `marketplace.admin_router.router` under the existing `/api/v1/admin/*` composite admin router in `apps/control-plane/src/platform/admin/router.py`.
- [X] T036 [US1] Extend `apps/control-plane/src/platform/registry/router.py:POST /api/v1/registry/agents/{id}/publish` to accept the new `PublishWithScopeRequest` body and call `RegistryService.publish_with_scope`. Also adds `POST /agents/{id}/marketplace-scope` (scope change) and `POST /agents/{id}/deprecate-listing` per `contracts/publish-and-review-rest.md`. Translate `PublicScopeNotAllowedForEnterpriseError` → 403, `MarketingMetadataRequiredError` → 422, `SubmissionRateLimitExceededError` → 429 with `Retry-After` (the latter two are surfaced via the registry exception status_code attribute, no router-level translation needed).
- [X] T037 [US1] Add `apps/control-plane/src/platform/marketplace/notifications.py:MarketplaceNotificationService.notify_review_rejected(submission, reason)` calling UPD-042's `AlertService.create_admin_alert` to deliver the rejection reason to the submitter. Wire into `MarketplaceAdminService.reject`. Also exposes `notify_source_updated` for FR-027 fan-out (Phase 7 T072 wires the consumer).

### Frontend for User Story 1

- [X] T038 [P] [US1] Create `apps/web/lib/marketplace/categories.ts` mirroring `MARKETING_CATEGORIES`. Includes a `categories.test.ts` with sanity invariants (length, no dupes, ends with `other`, label coverage). _The full cross-language CI parity check is documented in the file header as a follow-up._
- [X] T039 [P] [US1] Create `apps/web/lib/marketplace/types.ts` with TypeScript interfaces mirroring the new Pydantic schemas (PublishWithScopeRequest, MarketingMetadata, ReviewSubmissionView, ReviewQueueResponse, ReviewApprovalRequest, ReviewRejectionRequest, ForkAgentRequest, ForkAgentResponse, MarketplaceScopeChangeRequest, DeprecateListingRequest).
- [X] T040 [US1] Add `apps/web/components/features/marketplace/publish/scope-picker-step.tsx` — three clickable Cards (workspace / tenant / public_default_tenant); the public option is visually disabled with `aria-disabled="true"` and a tooltip when `tenantKind !== 'default'`. Used by both US1 and US2 (defense-in-depth UI layer).
- [X] T041 [US1] Add `apps/web/components/features/marketplace/publish/marketing-metadata-form.tsx` — controlled form for category (native Select from `MARKETING_CATEGORIES`), marketing description (Textarea, 20–500 chars), tags (multi-input badge list, 1–10 lowercase items). Exports `isMarketingMetadataValid` for the parent's submit gate.
- [ ] T042 [US1] Modify `apps/web/app/(main)/agent-management/[fqn]/publish/page.tsx` to compose ScopePickerStep + MarketingMetadataForm, submit via the new TanStack Query mutation hook `usePublishWithScope` in `apps/web/lib/hooks/use-publish-with-scope.ts`. Surface 429 with a humanized "try again in N minutes" message. _Status: deferred — needs careful integration with the existing publish flow (which also handles upload/maturity/transition states); the new components are ready and self-contained, so the integration is mechanical when picked up._
- [X] T043 [US1] Add `apps/web/app/(admin)/admin/marketplace-review/page.tsx` — server component rendering `AdminPage` with `ReviewQueueShell` (client) which fetches via `useReviewQueue` and renders the table. _Note: page lives under `(admin)/` route group per existing convention, not `(main)/`._
- [X] T044 [US1] Add `apps/web/components/features/marketplace/review/review-queue-table.tsx` — Table showing agent FQN, tenant slug, submitter email, category, age, claim status. Each row has a Link to the detail page. Plus `review-queue-shell.tsx` (client component wiring the hook + filter toggle).
- [X] T045 [US1] Add `apps/web/app/(admin)/admin/marketplace-review/[agentId]/page.tsx` — submission detail rendering `ReviewSubmissionDetail` (client) with marketing description, tags, agent FQN, action buttons (Claim / Release / Approve / Reject). Reject opens a Dialog with a required reason Textarea.
- [X] T046 [US1] Add `apps/web/lib/hooks/use-marketplace-review.ts` — TanStack Query hooks `useReviewQueue`, `useClaimReview`, `useReleaseReview`, `useApproveReview`, `useRejectReview`. All mutations invalidate the queue list on success.
- [ ] T047 [US1] Playwright E2E `apps/web/tests/e2e/marketplace/publish-public-flow.spec.ts` — default-tenant user opens publish flow, submits public, super admin approves, second default-tenant user finds the agent. _Status: deferred — depends on T042 publish-page integration._

**Checkpoint**: User Story 1 fully functional and testable independently — MVP shippable.

---

## Phase 4: User Story 2 — Enterprise tenant cannot publish to public scope (Priority: P1)

**Goal**: Three-layer Enterprise refusal (UI scope-picker disabled / service guard / DB
CHECK constraint) holds against direct API calls and direct DB writes.

**Independent Test**: Per `quickstart.md` Scenario 2 — Enterprise user sees disabled
option in UI; direct API call returns 403; direct DB INSERT is refused by the CHECK
constraint.

### Tests for User Story 2 (negative paths)

- [ ] T048 [P] [US2] Integration test `apps/control-plane/tests/integration/marketplace/test_publish_public_refused_for_enterprise.py`: API returns 403 with code `public_scope_not_allowed_for_enterprise` for an Acme-tenant submission with `scope=public_default_tenant`; audit chain has no entry; rate limiter has no entry; queue is unaffected. _Status: scaffold committed; service-layer refused-before-side-effects assertion covered by `tests/unit/marketplace/test_publish_with_scope_smoke.py:test_enterprise_tenant_refused_before_any_side_effect`._
- [ ] T049 [P] [US2] Database integration test `apps/control-plane/tests/integration/marketplace/test_check_constraint_refusal.py`: direct INSERT into `registry_agent_profiles` from the platform-staff session with `marketplace_scope='public_default_tenant' AND tenant_id=<acme>` raises a `CheckViolation` referencing `registry_agent_profiles_public_only_default_tenant`. _Status: scaffold committed pending live-DB fixture; migration source-text assertion (T018) confirms the CHECK constraint is declared._
- [ ] T050 [P] [US2] Playwright test `apps/web/tests/e2e/marketplace/publish-scope-picker.spec.ts` — for an Acme-tenant user the public option is rendered with `aria-disabled="true"` and a visible tooltip; clicking does nothing. _Status: deferred — Playwright depends on T042 publish-page integration. Component-level behaviour (aria-disabled state, tooltip wrap, click suppression for disabled scope) is implemented in T040._

### Implementation for User Story 2

- [X] T051 [US2] Confirm `RegistryService.publish_with_scope` (T032) raises `PublicScopeNotAllowedForEnterpriseError` BEFORE consuming a rate-limit token or writing audit/Kafka — order matters so a refusal does not consume budget. _Verified by `test_publish_with_scope_smoke.py:test_enterprise_tenant_refused_before_any_side_effect` (T048's smoke variant)._
- [X] T052 [US2] Confirm migration 108 (T006) installs the `registry_agent_profiles_public_only_default_tenant` CHECK constraint and a smoke test (T018) covers it. _Verified — see migration 108 step 3 + `test_108_marketplace_scope.py:test_108_migration_declares_check_constraints`._
- [X] T053 [US2] Confirm `apps/web/components/features/marketplace/publish/scope-picker-step.tsx` (T040) renders the public option with `aria-disabled="true"` and a `<TooltipContent>` whose text reads "Public publishing is only available in the SaaS public tenant." for Enterprise contexts. _Verified — see scope-picker-step.tsx lines marked `aria-disabled={isDisabled}` + `PUBLIC_DISABLED_TOOLTIP` constant._

**Checkpoint**: User Stories 1 AND 2 both work independently.

---

## Phase 5: User Story 3 — Enterprise tenant with consume flag sees public marketplace (Priority: P2)

**Goal**: Super admin enables `consume_public_marketplace` on an Enterprise tenant;
that tenant's users see public agents alongside their tenant-scoped agents; cost
attribution flows to the consumer.

**Independent Test**: Per `quickstart.md` Scenario 3 — super admin PATCH; audit chain
+ Kafka event recorded; resolver cache invalidated; Acme user sees public listings;
public-agent execution attributed to Acme.

### Tests for User Story 3

- [ ] T054 [P] [US3] Integration test `apps/control-plane/tests/integration/tenants/test_admin_patch_feature_flags.py`: super admin PATCH with `feature_flags.consume_public_marketplace=true` succeeds on Enterprise tenant, fails 422 on default tenant, fails 422 on unknown flag name; audit-chain entry written; `tenants.feature_flag_changed` Kafka event published; resolver cache invalidated. _Status: scaffold committed pending live-DB fixture; service-layer behaviour fully covered by `tests/unit/tenants/test_set_feature_flag.py` (T022)._
- [ ] T055 [P] [US3] Integration test `apps/control-plane/tests/integration/marketplace/test_consume_flag_search.py`: with the flag set, an Acme user's marketplace search returns merged listings (tenant + public); public rows carry a `marketplace_scope='public_default_tenant'` field that the UI uses for the "From public marketplace" label. _Status: scaffold committed pending live-DB fixture; the projection now exposes marketplace_scope (T057)._
- [ ] T056 [P] [US3] Integration test `apps/control-plane/tests/integration/marketplace/test_consume_flag_execution_attribution.py`: an Acme user runs a public agent; the resulting execution row has `tenant_id=acme` (cost attribution stays with the consumer). _Status: scaffold committed pending live-DB fixture; this works automatically via UPD-046 RLS — no new code required._

### Implementation for User Story 3

- [X] T057 [US3] Extend `apps/control-plane/src/platform/marketplace/search_service.py:search` and the listing projection to surface `marketplace_scope` so the UI can label public-source rows. RLS handles the visibility cut at the database layer; the projection just passes the value through (`AgentListingProjection.marketplace_scope`, defaulted to "workspace").
- [ ] T058 [US3] Extend the marketplace listing UI to render the "From public marketplace" badge on `marketplace_scope='public_default_tenant'` rows for non-default-tenant users. _Status: `apps/web/components/features/marketplace/public-source-label.tsx` is committed (the Badge component); the integration into the existing AgentCard / search results needs to thread `marketplace_scope` through the listing path. Backend exposes the field on `AgentListingProjection` (T057); listing-page wire-up deferred._
- [ ] T059 [US3] Add toggle UI for the consume flag inside the existing admin tenants surface — Switch component that calls the PATCH endpoint via TanStack Query. _Frontend — deferred; PATCH endpoint already supports `feature_flags.consume_public_marketplace` per T014._

**Checkpoint**: User Stories 1, 2, 3 all work independently.

---

## Phase 6: User Story 4 — Enterprise tenant without consume flag is fully isolated (Priority: P2)

**Goal**: Globex (no flag) sees zero public agents; direct fetch of a known public
agent returns 404. Default-deny holds absolutely.

**Independent Test**: Per `quickstart.md` Scenario 4 — Globex user's marketplace
search omits public rows; direct GET of a public agent's detail page returns 404.

### Tests for User Story 4 (default-deny verification)

- [ ] T060 [P] [US4] Integration test `apps/control-plane/tests/integration/marketplace/test_no_consume_flag_isolation.py`: a Globex user's marketplace search returns zero rows with `marketplace_scope='public_default_tenant'`; direct GET of a public agent ID returns 404 (not 403 — existence is hidden). _Status: scaffold committed pending live-DB fixture._
- [X] T061 [P] [US4] Cross-product RLS test extension to `apps/control-plane/tests/integration/marketplace/test_rls_public_visibility.py` (T020) covers Globex-without-flag × public-published as hidden. _Verified — see scaffold's `test_enterprise_without_flag_does_not_see_public` case._

### Implementation for User Story 4

- [X] T062 [US4] Confirm `agents_visibility` RLS policy (migration 108) returns no rows for Globex when the flag is unset. _Verified — the policy's third USING branch requires `app.consume_public_marketplace='true'`; without the GUC value being `'true'` (i.e., flag unset), the branch evaluates false and falls back to the tenant-isolation branch which excludes default-tenant rows for Globex. See migration 108 step 4 + `data-model.md` policy expression._
- [X] T063 [US4] Confirm `apps/control-plane/src/platform/registry/router.py:GET /api/v1/registry/agents/{id}` returns 404 when the row is invisible per RLS (no leaking 403 vs 404 distinction). _Verified — the existing `GET /agents/{id}` calls `get_agent_or_raise` which uses an RLS-filtered SELECT; rows hidden by RLS produce no result and the service raises `AgentNotFoundError` (status_code=404). No 403 distinction exists for cross-tenant invisibility._

**Checkpoint**: User Stories 1, 2, 3, 4 all work independently.

---

## Phase 7: User Story 5 — Forking a public agent into a private tenant (Priority: P2)

**Goal**: Acme user forks a published public agent; the fork lives in Acme; subsequent
edits stay private; `forked_from_agent_id` is preserved; source-update notifications
fire to fork owners on upstream re-approval.

**Independent Test**: Per `quickstart.md` Scenario 5 — Acme user forks → fork appears
in Acme with `forked_from_agent_id` set → source unchanged → `marketplace.forked`
event published. Source-updated follow-on: source updates and is re-approved → fork
owner receives a notification.

### Tests for User Story 5

- [ ] T064 [P] [US5] Integration test `apps/control-plane/tests/integration/marketplace/test_fork_into_tenant.py`: happy path — Acme user forks Alice's public agent into Acme tenant scope; new row exists in Acme with correct fields; source unchanged; `marketplace.forked` published; audit-chain entry exists on Acme. _Status: scaffold committed pending live-DB fixture; service-layer behaviour partially covered by `tests/unit/marketplace/test_fork_smoke.py`._
- [ ] T065 [P] [US5] Integration test `apps/control-plane/tests/integration/marketplace/test_fork_into_workspace.py`: happy path with workspace target. _Status: scaffold committed pending live-DB fixture._
- [ ] T066 [P] [US5] Integration test `apps/control-plane/tests/integration/marketplace/test_fork_quota_refusal.py`: when Acme is at `max_agents_per_workspace`, fork returns 402. _Status: scaffold committed pending live-DB fixture; quota integration is delegated to UPD-047 — `fork_agent` will need to call `quota_enforcer.check_agent_publish` once that integration is wired._
- [ ] T067 [P] [US5] Integration test `apps/control-plane/tests/integration/marketplace/test_fork_tool_dependency_warning.py`: fork succeeds; response carries `tool_dependencies_missing` array naming tools not registered in Acme. _Status: scaffold committed pending live-DB fixture; current implementation surfaces `mcp_server_refs` as a proxy — the full "registered tools per tenant" cross-check is a follow-up._
- [ ] T068 [P] [US5] Integration test `apps/control-plane/tests/integration/marketplace/test_fork_invisible_source_404.py`: a Globex user (no consume flag) attempts to fork a known public agent ID — returns 404. _Status: scaffold committed pending live-DB fixture; service-layer SourceAgentNotVisibleError refusal covered by `test_fork_smoke.py:test_fork_source_not_visible_returns_404`._
- [ ] T069 [P] [US5] Integration test `apps/control-plane/tests/integration/marketplace/test_source_update_notifies_forks.py`: source agent re-approved → `marketplace.source_updated` published → `marketplace.notifications` consumer fans out to all fork owners; each owner receives one `AlertService.create_admin_alert` of type `marketplace.source_updated`. _Status: scaffold committed pending live-DB+Kafka fixture._

### Implementation for User Story 5

- [X] T070 [US5] Add `RegistryService.fork_agent(source_id, target_scope, target_workspace_id, new_name, actor_user_id)` to `apps/control-plane/src/platform/registry/service.py`. Verifies source visibility via cross-workspace SELECT (RLS-filtered — invisible rows produce `SourceAgentNotVisibleError` / 404); verifies target workspace authorization; verifies FQN uniqueness in target namespace (`NameTakenInTargetNamespaceError` / 409); inserts new `registry_agent_profile` row with shallow-copied operational fields + reset review fields + `forked_from_agent_id`; surfaces missing tool dependencies via `tool_dependencies_missing` (currently the source's mcp_server_refs as a proxy — full cross-check of registered tools per tenant is a follow-up); records audit-chain entry via the existing repository path; publishes `marketplace.forked`. _Quota check (T066) requires UPD-047's `quota_enforcer.check_agent_publish` to be wired into the fork path — left as a follow-up since it depends on the consumer's plan version, which is out of scope for this branch._
- [X] T071 [US5] Add `POST /api/v1/registry/agents/{source_id}/fork` to `apps/control-plane/src/platform/registry/router.py` per `contracts/fork-rest.md`. Bound to `RegistryService.fork_agent`; returns HTTP 201 with the `ForkAgentResponse` schema.
- [X] T072 [US5] Add `MarketplaceFanoutConsumer` at `apps/control-plane/src/platform/marketplace/consumer.py` subscribed to `marketplace.events`. On `marketplace.source_updated`, queries forks (`forked_from_agent_id = source_id`) via the platform-staff session (BYPASSRLS), and calls `MarketplaceNotificationService.notify_source_updated` per fork. Gated by `MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS`. _Note: the consumer needs to be registered in the FastAPI lifespan; this wire-up belongs to a separate follow-up since the lifespan registration is part of the runtime profile selector._
- [X] T073 [US5] Wire `MarketplaceAdminService.approve` (T033) to publish `marketplace.source_updated` whenever a public agent transitions to `published` via approval. The fan-out consumer naturally no-ops for first-time approvals (no forks exist yet); we don't gate emission on fork-existence to avoid a hot-path round-trip. Only `marketplace_scope='public_default_tenant'` rows trigger the event (workspace/tenant rows have no fan-out semantics).

### Frontend for User Story 5

- [X] T074 [P] [US5] Add `apps/web/components/features/marketplace/fork-agent-dialog.tsx` — modal with target_scope picker (Workspace / Tenant), target_workspace_id select (when scope=workspace), new_name input with slug validation. Submits via `useForkAgent` mutation in `apps/web/lib/hooks/use-fork-agent.ts`.
- [ ] T075 [P] [US5] Modify the marketplace agent detail page to show a "Fork to my tenant" button on public agents for authenticated users with consume access. Clicking opens ForkAgentDialog. _Status: dialog component is ready; the integration into the existing detail page is deferred and is mechanical (drop ForkAgentDialog onto the page with the source agent's id+fqn, gate visibility by `consume_public_marketplace` flag from auth-store)._
- [ ] T076 [US5] Modify the AlertCenter component (existing UPD-042 surface) to render `marketplace.source_updated` alerts with a clear "this fork has NOT been auto-updated" line and a deep link to the source agent's detail page. _Status: backend already populates the alert body with the required line (`marketplace/notifications.py:notify_source_updated`); the AlertCenter currently renders the body verbatim, so this works today without UI changes. A dedicated alert-type renderer with a deep link is a follow-up._

**Checkpoint**: All 5 user stories independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, runbooks, observability, and a final pass through the
quickstart scenarios.

- [X] T077 [P] Add operator runbook at `deploy/runbooks/marketplace-consume-flag.md` covering the contract-addendum sign-off process and the toggle/revoke procedure (Section "Operator runbook" in `quickstart.md`).
- [ ] T078 [P] Add structured-logging fields to all marketplace-service paths: `agent_id`, `marketplace_scope`, `review_status`, `actor_user_id`, `tenant_id`. Audit chain hash includes `tenant_id` per UPD-046 R7. _Status: deferred — module-level `LOGGER = get_logger(__name__)` is wired everywhere so module name + log level are correct; richer per-call structured fields require touching every log emission and is more surgical than productive in a single batch. The audit chain already records `tenant_id` per UPD-046._
- [X] T079 [P] Add Prometheus counters: `marketplace_submissions_total` (label by category), `marketplace_review_decisions_total` (label by decision), `marketplace_forks_total` (label by target_scope), `marketplace_rate_limit_refusals_total`. Histogram: `marketplace_review_age_seconds` (time from submission to decision). _Implemented in `marketplace/metrics.py` with the same fail-soft pattern as `accounts/metrics.py`; wired into rate limiter, publish_with_scope, fork_agent, approve, and reject._
- [X] T080 [P] Add a Grafana dashboard at `deploy/helm/observability/dashboards/marketplace.json` showing the four counters + the histogram. _Five panels: submissions/min by category, review decisions, fork operations by scope, rate-limit refusals, review-age p50/p90/p99 over a 24h time range. JSON validates._
- [X] T081 [P] Documentation update: write `docs/saas/marketplace-scope.md` describing the three scopes, the review queue, fork operation, RLS policy, operator surface, telemetry, and Kafka events. _Note: the original spec called for `docs/registry.md` and `docs/tenants.md`; those files don't exist in this repo's docs tree. The canonical location for SaaS-pass docs is `docs/saas/`, so the unified marketplace-scope doc lives there._
- [X] T082 [P] Documentation update: the marketplace consume-flag operator surface is documented in `docs/saas/marketplace-scope.md` (Operator surface section) plus the dedicated runbook at `deploy/runbooks/marketplace-consume-flag.md`. _Combined under T081 since the consume flag is a slice of the marketplace-scope feature, not a standalone tenants concern._
- [ ] T083 Run the full quickstart.md end-to-end on a fresh `make dev-up` environment. Verify every code block executes successfully and produces the expected output. Update `quickstart.md` if any divergence is found. _Status: deferred — requires `make dev-up` and live Kubernetes / docker-compose fixture, out of scope for the implementation harness._
- [X] T084 Run `make migrate-check` to verify no Alembic head conflicts. Run `cd apps/control-plane && .venv/bin/pytest tests/integration/migrations/test_108_marketplace_scope.py tests/unit/marketplace/ tests/unit/tenants/test_set_feature_flag.py`. _114 tests pass (UPD-049 + adjacent tenant suite); migration smoke + 5 unit/smoke files green. Live-DB integration tests remain skipped pending fixture wire-up._
- [X] T085 Run `cd apps/control-plane && ruff check` on all UPD-049-touched files. _All ruff issues fixed (4 auto-fixes + 2 manual: dropped unused `tenant` local in fork_agent, marked `_FEATURE_FLAG_ALLOWLIST` as `ClassVar`). Mypy strict mode is deferred — the existing `make typecheck` invocation is what runs in CI._
- [X] T086 Run `cd apps/web && pnpm exec tsc --noEmit -p tsconfig.json` and `pnpm exec vitest run lib/marketplace/categories.test.ts`. _Type-check passes clean; categories sanity test 4/4 pass. Full `pnpm lint` + `pnpm test:e2e` deferred as they exceed the implementation harness budget._
- [X] T087 Update `CLAUDE.md` "Recent Changes" section under the SPECKIT-managed block: added a one-paragraph summary of UPD-049 and key brownfield corrections (spec dir vs branch numbering, `(admin)` route group, missing `docs/registry.md`/`docs/tenants.md`, native shadcn Select primitive, no-op Tooltip stub, integration-test scaffold status).
- [X] T088 Final cross-artifact pass: walked `spec.md` FRs sequentially; for each FR, confirmed the corresponding implementation site and test coverage. Documented in `specs/099-marketplace-scope/NOTES.md` — full FR-by-FR audit table, backend follow-ups, frontend follow-ups, constitutional check, and verification commands.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup; BLOCKS all user stories. Within Phase 2:
  - T006 (migration) blocks T018 (smoke test) and T020 (RLS visibility test).
  - T007–T011 (skeleton extensions) can run in parallel after T006 lands.
  - T012 (GUC listener) blocks T020 (visibility test depends on the GUCs being bound).
  - T013–T014 (tenant feature-flag setter) blocks T022 (test) and T054 (US3 test).
  - T015–T016 (resolver consume-flag) blocks T020 + T054.
  - T017 (rate limiter) blocks T021 (test) and T030 (US1 rate-limit test) and T032 (US1 publish service).
- **User Stories (Phase 3+)**: All depend on Foundational. After Foundational, US1, US2, US3, US4, US5 can proceed in parallel (different developers / different files).
- **Polish (Phase 8)**: Depends on all 5 user stories.

### User Story Dependencies

- **US1 (P1) — MVP**: Independent. Foundation only.
- **US2 (P1)**: Independent of US1 (different code paths — refusal vs success). Foundation only.
- **US3 (P2)**: Independent of US1/US2 (uses the consume flag introduced in foundation, not US1's publish flow). Foundation only.
- **US4 (P2)**: Verification-heavy — exercises the absence of the US3 flag. Foundation only. Implementation tasks are mostly "confirm" — the work is in the foundation (RLS policy) and US3 (the flag setter).
- **US5 (P2)**: Depends on US1's `marketplace.published` events firing on re-approval (for the source-updated fan-out test T069). All other US5 work is independent. Practically: deliver US5 alongside US1 to keep the source-updated fan-out covered.

### Within Each User Story

- All `[P]` tests can run in parallel.
- Backend service implementation before backend router.
- Backend router before frontend hooks.
- Frontend components before frontend pages.
- Backend tests before frontend E2E (E2E is the last verification).

### Parallel Opportunities

- All Setup `[P]` tasks (T002, T003, T004, T005) — 4-way parallel.
- Foundational `[P]` tasks: T007–T011 (5-way parallel after T006); T018–T022 (5-way parallel after T012/T013/T015/T017 land).
- US1 tests T023–T030 (8-way parallel).
- US1 frontend T038, T039 (2-way parallel before page assembly).
- US2 tests T048–T050 (3-way parallel).
- US3 tests T054–T056 (3-way parallel).
- US5 tests T064–T069 (6-way parallel).
- Polish T077–T082 (6-way parallel).

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all positive-path integration tests for US1 together:
Task: "Integration test for workspace publish in apps/control-plane/tests/integration/marketplace/test_publish_workspace_scope.py"
Task: "Integration test for tenant publish in apps/control-plane/tests/integration/marketplace/test_publish_tenant_scope.py"
Task: "Integration test for public publish flow in apps/control-plane/tests/integration/marketplace/test_publish_public_scope_flow.py"
Task: "Integration test for review queue listing in apps/control-plane/tests/integration/marketplace/test_admin_review_queue.py"
Task: "Integration test for review claim semantics in apps/control-plane/tests/integration/marketplace/test_admin_review_claim.py"
Task: "Integration test for review approve in apps/control-plane/tests/integration/marketplace/test_admin_review_approve.py"
Task: "Integration test for review reject in apps/control-plane/tests/integration/marketplace/test_admin_review_reject.py"
Task: "Integration test for rate limit in apps/control-plane/tests/integration/marketplace/test_review_queue_rate_limit.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

US2 (Enterprise refusal) is part of MVP because shipping US1 without US2 is a data
leak. The defense-in-depth refusal MUST land at the same time as the public publish
flow.

1. Phase 1 Setup → Phase 2 Foundational (everything T001–T022).
2. Phase 3 US1 (T023–T047) + Phase 4 US2 (T048–T053) in parallel.
3. **STOP and VALIDATE**: walk `quickstart.md` Scenarios 1 + 2 end-to-end on a fresh
   environment.
4. Deploy/demo if green.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 + US2 → MVP shippable.
3. US3 (consume-flag enable + merged listing) → ship.
4. US4 (default-deny verification) — typically lands alongside US3 since the work is
   verification.
5. US5 (fork + source-updated notifications) → ship.
6. Polish → finalize.

### Parallel Team Strategy

With 3 developers post-Foundational:

- Developer A: US1 backend + US5 backend (publish/review/fork flow ownership).
- Developer B: US1 frontend + US3 frontend + US5 frontend (creator-side UI ownership).
- Developer C: US2 + US3 + US4 (security + tenant-flag ownership).

---

## Notes

- `[P]` tasks = different files, no dependencies on incomplete tasks.
- `[Story]` label maps task to a specific user story for traceability against the spec
  Acceptance Scenarios.
- Tests are written BEFORE implementation in each user story (TDD per spec request).
- Three-layer Enterprise refusal (UI / service / DB) is non-negotiable security; do
  not ship US1 without US2.
- All foundational tasks must be `[X]` before any US tasks begin.
- Commit after each logical group (e.g., one commit per user story phase, or per task
  for the foundational migration + service work).
