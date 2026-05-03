---

description: "Tasks: UPD-049 Marketplace Scope (Refresh Pass on 099 Baseline)"
---

# Tasks: UPD-049 Marketplace Scope (Refresh Pass on 099 Baseline)

**Input**: Design documents from `/specs/102-marketplace-scope/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ (4 files) ✅, quickstart.md ✅
**Baseline**: `specs/099-marketplace-scope/` is merged via PR #133 — this refresh is additive on top of that work.

**Tests**: Tests are IN SCOPE for this refresh because the spec defines explicit testable success criteria (SC-001 through SC-009) and research.md R13 commits to un-skipping the 18 integration tests scaffolded by 099. Each user story phase below ends with the integration/E2E tests that lock its success criterion.

**Organization**: Tasks are grouped by user story (US1–US5 from spec.md). Most stories can be implemented independently; the foundational Phase 2 must complete first.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1/US2/US3/US4/US5)
- All file paths absolute from repo root

## Path Conventions

- **Backend control plane**: `apps/control-plane/src/platform/...`
- **Backend tests**: `apps/control-plane/tests/...`
- **Frontend**: `apps/web/...`
- **Migrations**: `apps/control-plane/migrations/versions/...`
- **Helm**: `deploy/helm/...`
- **Docs**: `docs/saas/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Confirm the 099 baseline is healthy and the workspace is ready for the refresh.

- [X] T001 Verify 099 baseline by running `make migrate-check` and confirming Alembic head is `108_marketplace_scope_and_review`. Document the head hash in `specs/102-marketplace-scope/NOTES.md` as the starting point.
- [X] T002 [P] Verify the `MarketplaceFanoutConsumer` is currently NOT registered in any entrypoint by running `grep -rn MarketplaceFanout apps/control-plane/entrypoints/` and confirming zero matches (this is the 099 NOTES item we close in T010).
- [X] T003 [P] Run the existing 099 smoke test suite (`pytest apps/control-plane/tests/unit/marketplace/ -v`) and confirm all pass. This baselines the refresh — any pre-existing failure must be triaged before refresh work begins.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema + foundational classes + consumer wiring + integration-test fixture. **No user story phase below can begin until this phase is complete.**

- [X] T004 Create Alembic migration `apps/control-plane/migrations/versions/109_marketplace_reviewer_assignment.py` per `data-model.md` § Migration outline. Single column `assigned_reviewer_user_id UUID NULL`, FK `users.id ON DELETE SET NULL`, partial index `registry_agent_profiles_assignee_pending_idx WHERE review_status = 'pending_review'`. Verify `make migrate` then `make migrate-rollback` round-trips cleanly.
- [X] T005 [P] Add `assigned_reviewer_user_id` mapped column to `apps/control-plane/src/platform/registry/models.py:AgentProfile`. Match the migration column type and nullability.
- [X] T006 [P] Add 4 new exception classes to `apps/control-plane/src/platform/marketplace/exceptions.py`: `SelfReviewNotAllowedError(PlatformError)` (HTTP 403, code `self_review_not_allowed`), `ReviewerAssignmentConflictError` (HTTP 409, code `assignment_conflict`), `PublicAgentNotFoundForConsumerError` (HTTP 404, code `agent_not_found` — same code as generic not-found per FR-741.10), `MarketplaceParityViolationError` (HTTP 500, code `parity_probe_setup_failed` — only raised by the dev-only probe path).
- [X] T007 [P] Add 2 new Kafka event types to `apps/control-plane/src/platform/marketplace/events.py`: `MarketplaceReviewAssignedEvent` and `MarketplaceReviewUnassignedEvent`. Payloads per `contracts/marketplace-events-kafka.md`. Producer reuses the existing `EventEnvelope` helper.
- [X] T008 [P] Add 1 new audit-chain entry kind constant `marketplace.review.self_review_attempted` to `apps/control-plane/src/platform/security_compliance/services/audit_chain_service.py` (or wherever audit kinds are catalogued). Audit-only; no Kafka event.
- [X] T009 Register `MarketplaceFanoutConsumer` in `apps/control-plane/entrypoints/worker_main.py` lifespan. One-line addition after the existing consumer registrations: `marketplace_fanout_consumer.register(consumer_manager)`. Imports the consumer from `platform.marketplace.consumer`. Closes 099 NOTES item 3.
- [X] T010 Wire the live-DB+Kafka integration fixture into `apps/control-plane/conftest.py` under a new pytest mark `integration_live`. Delegate to feature-071's existing `tests/e2e/conftest.py` fixtures (`db`, `kafka_consumer`, `http_client`). Add the mark to `pytest.ini` or `pyproject.toml`. Per R13.

**Checkpoint**: Schema migrated, model updated, exceptions/events/audit kinds defined, consumer registered, integration fixture available. User story phases can now proceed in parallel.

---

## Phase 3: User Story 1 — Default-tenant creator publishes an agent to the public hub (Priority: P1) 🎯 MVP

**Goal**: A creator submits a public-scope agent, a platform-staff reviewer receives the assignment + claims + approves (or rejects with reason), the submitter is notified on rejection, and the agent appears in the public marketplace on approval. Self-review is refused at every action.

**Independent Test**: A default-tenant creator publishes an agent at `public_default_tenant` scope. A reviewer-lead assigns it to a specific platform-staff reviewer. The reviewer claims and approves it. Two minutes later, a second default-tenant user (different workspace) sees the agent in the marketplace. A second submission is rejected with reason; the submitter receives a notification. A self-authored approve attempt returns HTTP 403 `self_review_not_allowed`.

**Maps to**: FR-733, FR-734, FR-735, FR-736, FR-737, FR-738, FR-739, FR-740, FR-741.8, FR-741.9. Success criteria: SC-001, SC-007, SC-008, SC-009.

### Backend — self-review prevention (R9)

- [X] T011 [P] [US1] Add `_ensure_not_self_review(agent_id, actor_user_id, *, action)` private helper to `apps/control-plane/src/platform/marketplace/review_service.py`. Reads submitter via repository, raises `SelfReviewNotAllowedError` and emits `marketplace.review.self_review_attempted` audit-chain entry on match. Per `contracts/self-review-prevention.md`.
- [X] T012 [US1] Wire `_ensure_not_self_review` as the first I/O step in `MarketplaceReviewService.claim`, `.approve`, and `.reject` in `apps/control-plane/src/platform/marketplace/review_service.py`. Action verb argument is the literal `"claim"`, `"approve"`, or `"reject"` respectively. Depends on T011.
- [X] T013 [P] [US1] Add `ensure_not_self_review_dependency` FastAPI dependency to `apps/control-plane/src/platform/marketplace/dependencies.py`. Reads `agent_id` from path, `actor_user_id` from auth context, calls service-layer helper synchronously. Defense-in-depth per R9.
- [X] T014 [US1] Apply the new dependency to the existing 4 review routes in `apps/control-plane/src/platform/marketplace/admin_router.py`: `claim`, `approve`, `reject`, plus the new `assign` endpoint added in T016. Depends on T013.

### Backend — reviewer assignment (R11)

- [X] T015 [P] [US1] Add `assign(agent_id, reviewer_user_id, assigner_user_id)` and `unassign(agent_id, assigner_user_id)` methods to `apps/control-plane/src/platform/marketplace/review_service.py`. Per `data-model.md` state machine. Calls `_ensure_not_self_review` (verb `"assign"`) on assign; emits Kafka events; writes audit chain entries. Depends on T011.
- [X] T016 [US1] Add `POST /api/v1/admin/marketplace-review/{agent_id}/assign` and `DELETE /api/v1/admin/marketplace-review/{agent_id}/assign` routes to `apps/control-plane/src/platform/marketplace/admin_router.py`. Both gated by `require_superadmin`. Per `contracts/reviewer-assignment-rest.md`. Depends on T015.
- [X] T017 [US1] Update `MarketplaceReviewService.claim` in `apps/control-plane/src/platform/marketplace/review_service.py` to refuse with `ReviewerAssignmentConflictError` (HTTP 409) when `assigned_reviewer_user_id` is set and not equal to the claimant. Preserves today's "anyone can claim" workflow when assignment is unset. Depends on T015.
- [X] T018 [P] [US1] Add 3 new schemas to `apps/control-plane/src/platform/marketplace/schemas.py`: `AssignReviewerRequest`, `ReviewerAssignmentResponse`, `ReviewerUnassignmentResponse`. Per `contracts/reviewer-assignment-rest.md`.
- [X] T019 [US1] Extend `MarketplaceReviewService.list_queue` in `apps/control-plane/src/platform/marketplace/review_service.py` to project `assigned_reviewer_user_id`, `assigned_reviewer_email` (LEFT JOIN `users`), and `is_self_authored` (computed). Add query parameters `assigned_to` (UUID | `me` | `unassigned`) and `include_self_authored` (default `false`) to the list endpoint signature. Depends on T015 and T005.

### Backend — rejection notifications via UPD-042 (FR-741.8 / SC-008)

- [X] T020 [P] [US1] Replace the inline `notify_review_rejected` shim in `apps/control-plane/src/platform/marketplace/notifications.py` with a call to the canonical user-notification channel established by UPD-042 (spec 092). Depends on the existing `notifications.event_dispatcher` interface. Subject and body per the existing 099 implementation; only the delivery channel changes.

### Frontend — review queue assignment + self-review gating

- [X] T021 [P] [US1] Create `apps/web/components/features/marketplace/review/ReviewQueueAssignmentControls.tsx`. Renders Assign/Unassign buttons + reviewer-selector dropdown. Calls the TanStack Query mutation hook from T024. Filters submitter out of the assign-target dropdown.
- [X] T022 [P] [US1] Create `apps/web/components/features/marketplace/review/ReviewQueueFilterChips.tsx`. Three chips: "Unassigned", "Assigned to me", "Assigned to others". Updates the URL query param `assigned_to`.
- [X] T023 [US1] Update `apps/web/app/(admin)/admin/marketplace-review/page.tsx` to (a) render the new "Assigned to" column with assignee email or `—`, (b) render a "Self-authored" badge when `is_self_authored=true`, (c) integrate `ReviewQueueFilterChips`. Depends on T021, T022.
- [X] T024 [P] [US1] Create `apps/web/lib/hooks/use-reviewer-assignment.ts` with TanStack Query mutation hooks `useAssignReviewer` and `useUnassignReviewer`. Optimistic update on the queue cache; rollback on 409. Per `contracts/reviewer-assignment-rest.md`.
- [X] T025 [US1] Update `apps/web/app/(admin)/admin/marketplace-review/[agentId]/page.tsx` to (a) render an Assignment card with Assign/Unassign action, (b) disable Approve/Reject/Claim buttons when `is_self_authored=true` with a "you authored this submission" tooltip. Depends on T021, T024.

### Frontend — publish-page rewire (closes 099 T042)

- [X] T026 [US1] Update `apps/web/app/(main)/agent-management/[fqn]/publish/page.tsx` to compose the existing `ScopePickerStep` and `MarketingMetadataForm` components from 099. Gate the Submit button on `isMarketingMetadataValid` when scope is `public_default_tenant`. Surface 429 (rate-limit) with a humanised message. Closes 099 NOTES Frontend follow-up 1.

### Tests — US1

- [X] T027 [P] [US1] Add `apps/control-plane/tests/unit/marketplace/test_self_review_guard.py`. Table-driven test for `_ensure_not_self_review` with the four action verbs (`assign`, `claim`, `approve`, `reject`). Asserts the audit-chain entry is emitted with both user IDs. No DB needed — uses a stub repository.
- [X] T028 [P] [US1] Add `apps/control-plane/tests/integration/marketplace/test_self_review_prevention.py` (under `integration_live` mark). For each of the four routes, assert (a) HTTP 403 with code `self_review_not_allowed`, (b) audit entry present, (c) no Kafka event emitted, (d) row state unchanged. Per `contracts/self-review-prevention.md` § Tests.
- [X] T029 [P] [US1] Add `apps/control-plane/tests/integration/marketplace/test_assignment_lifecycle.py` (under `integration_live` mark). Covers: assign by lead, idempotent re-assign same reviewer, 409 conflict on different reviewer, unassign idempotent, claim refused on assignment mismatch, claim succeeds when assigned to claimant. Asserts Kafka events `marketplace.review.assigned` / `unassigned` emitted with correct payloads.
- [X] T030 [US1] Remove `pytest.mark.skipif(True, ...)` markers from the 099-scaffolded integration tests at `apps/control-plane/tests/integration/marketplace/test_publish_with_scope.py`, `test_review_claim_release.py`, `test_review_approve_reject.py`. Replace with the new `integration_live` mark. Tests should now run end-to-end against the live-DB+Kafka fixture from T010. Closes 099 T023–T030.
- [X] T031 [P] [US1] Add `apps/web/tests/e2e/marketplace/review-queue-assignment.spec.ts` (Playwright). Asserts: lead can assign, assignee sees deep-link in inbox, claim-jumping by non-assignee returns 409, self-authored row's action buttons are disabled.
- [X] T032 [P] [US1] Add `apps/web/tests/e2e/marketplace/publish-flow.spec.ts` (Playwright). Asserts the publish flow with scope picker + marketing metadata form end-to-end (from `/agent-management/[fqn]/publish` to queue arrival). Closes 099 T047.
- [X] T033 [P] [US1] Add Grafana panel "Submission to approve median wall time" to `deploy/helm/observability/templates/dashboards/marketplace.yaml` (SC-001). Source: ClickHouse query over `marketplace.review.submitted` and `marketplace.review.approved` event timestamps.
- [X] T034 [P] [US1] Add Grafana panel "Review queue listing p95" (SC-007) and "Rejection notification delivery p95" (SC-008) to the same dashboard. Sources: Prometheus histogram for endpoint latency, Loki query for `notifications.review_rejected` event timestamps.

**Checkpoint**: US1 fully functional and testable independently. Self-review guard active at every layer. Reviewer assignment works. Submitters get notified on rejection via UPD-042. Publish flow rewired.

---

## Phase 4: User Story 2 — Enterprise-tenant user is prevented from publishing publicly (Priority: P1)

**Goal**: Confirm the 099 three-layer Enterprise refusal still works end-to-end after the refresh, and lock it with regression tests un-skipped from 099's scaffolds.

**Independent Test**: An Enterprise-tenant user opens the publish flow (public option disabled). The user posts a public-scope publish request via API and receives HTTP 403 with code `tenant_kind_not_default_tenant`.

**Maps to**: FR-741. Success criterion: SC-002.

### Tests — US2 (no new code; un-skip 099 regression tests)

- [X] T035 [P] [US2] Remove `pytest.mark.skipif(True, ...)` markers from `apps/control-plane/tests/integration/marketplace/test_enterprise_publish_refusal.py`. Replace with `integration_live` mark. Asserts the API-layer refusal returns 403 with the right code, no state change, audit-chain entry recorded. Closes 099 T048–T049.
- [X] T036 [P] [US2] Remove skip marker from `apps/control-plane/tests/integration/marketplace/test_db_check_constraint_public_only_default_tenant.py`. Asserts the database-layer CHECK constraint refuses a raw INSERT with `marketplace_scope='public_default_tenant' AND tenant_id != default_tenant_uuid`.
- [X] T037 [P] [US2] Add `apps/web/tests/e2e/marketplace/enterprise-cannot-publish-public.spec.ts` (Playwright). Asserts the public scope option is rendered with `aria-disabled` and a tooltip; selects a non-default-tenant test JWT for the user.

**Checkpoint**: US2's three-layer refusal is locked by regression tests. SC-002 verifiable on every CI run.

---

## Phase 5: User Story 3 — Enterprise tenant with consume flag sees public agents (Priority: P2)

**Goal**: An Enterprise tenant with `consume_public_marketplace=true` sees public agents alongside their own in browse, can run them, and the resulting cost event is attributed to the consuming tenant.

**Independent Test**: Per spec.md US3 Independent Test. Plus: a ClickHouse query after a public-agent invocation by an Acme user shows `tenant_id = acme_tenant_uuid` on the cost event.

**Maps to**: FR-741.1, FR-741.2, FR-741.3, FR-741.4. Success criteria: SC-003, SC-005.

### Frontend — visibility surfacing

- [X] T038 [P] [US3] Update `apps/web/app/(main)/marketplace/page.tsx` to thread `marketplace_scope` through the projection and render `PublicSourceLabel` (committed in 099) on cards owned by the default tenant when the consumer is non-default. Closes 099 NOTES Frontend follow-up 3 (T058).
- [X] T039 [P] [US3] Update `apps/web/app/(admin)/admin/tenants/[id]/feature-flags/page.tsx` (or create if absent) to render a Switch component for `consume_public_marketplace`. Calls the existing PATCH endpoint on `/api/v1/admin/tenants/{id}/feature-flags`. Closes 099 NOTES Frontend follow-up 4 (T059).
- [X] T040 [P] [US3] Update the marketplace agent detail page at `apps/web/app/(main)/marketplace/[namespace]/[name]/page.tsx` to hide Edit affordances when the viewer's tenant is non-default and the agent's tenant is the default tenant. Only Run, Inspect, and Fork remain available (FR-741.3).

### Backend — cost-attribution lock (SC-005)

- [X] T041 [P] [US3] Add an integration test at `apps/control-plane/tests/integration/marketplace/test_cost_attribution_consumer.py` (under `integration_live` mark). Drives a public-agent invocation by an Acme tenant user, then queries ClickHouse `cost_events` and asserts `tenant_id = acme_tenant_uuid`. Per R14.

### Tests — US3

- [X] T042 [P] [US3] Remove skip markers from `apps/control-plane/tests/integration/marketplace/test_consume_flag_visibility.py`. Asserts merged result set, badge labelling on the projection, and that disabling the flag mid-session updates new responses. Closes 099 T054–T056.
- [X] T043 [P] [US3] Add `apps/web/tests/e2e/marketplace/consumer-flag-rendering.spec.ts` (Playwright). Asserts: public agent cards render with the "From public marketplace" badge for an Acme user with the flag; same agents are absent for the same Acme user when the flag is off (cleared mid-session via the admin toggle).

**Checkpoint**: US3 fully functional. Cost attribution locked by regression. Public source label visible. Edit affordances correctly hidden.

---

## Phase 6: User Story 4 — Enterprise tenant without consume flag sees only its own (Priority: P2)

**Goal**: A no-consume-flag Enterprise tenant cannot see, count, or infer the existence of public agents through any surface (browse, search, suggestions, analytics, direct identifier lookup).

**Independent Test**: Per spec.md US4 Independent Test. Plus: the dev-only parity probe returns `parity_violation: false` for every term in the test corpus.

**Maps to**: FR-741.10. Success criterion: SC-004.

### Backend — parity probe (R10)

- [X] T044 [P] [US4] Create `apps/control-plane/src/platform/marketplace/parity_probe.py`. Service class `MarketplaceParityProbe` with one async method `run(query, subject_tenant_id) -> ParityProbeResult`. Implementation per `contracts/non-leakage-parity-probe-rest.md` § Behaviour: counter-factual run, savepoint-wrapped synthetic publish, live run, byte-equality compare, savepoint rollback. Raises `MarketplaceParityViolationError` on rollback failure.
- [X] T045 [US4] Add `GET /api/v1/admin/marketplace-review/parity-probe` route to `apps/control-plane/src/platform/marketplace/admin_router.py`. Gated by `require_superadmin` AND a check that returns 404 when `FEATURE_E2E_MODE != true`. Per `contracts/non-leakage-parity-probe-rest.md`. Depends on T044.
- [X] T046 [P] [US4] Add `MarketplaceParityProbeResult` Pydantic schema and `MarketplaceParityProbeQuery` schema to `apps/control-plane/src/platform/marketplace/schemas.py`. Per the contract.

### Backend — visibility filter pre-query layer (R10)

- [X] T047 [US4] Audit `apps/control-plane/src/platform/marketplace/search_service.py` to assert the visibility filter is applied BEFORE the result-count emission, the suggestion array emission, and the analytics-event emission. Refactor the order if any of these surfaces emit before the filter is applied. The audit must produce a written `## Visibility-Filter Audit` section appended to `specs/102-marketplace-scope/NOTES.md` documenting the order of each surface.

### Tests — US4

- [X] T048 [P] [US4] Add `apps/control-plane/tests/integration/marketplace/test_non_leakage_parity.py` (under `integration_live` mark). For each of 5 canonical query terms in the test corpus, drives the dev-only parity probe and asserts `parity_violation = false` and `parity_violations = []`. Per the SC-004 verification harness.
- [X] T049 [P] [US4] Add `apps/control-plane/tests/integration/marketplace/test_parity_probe_404_in_production.py` (under `integration_live` mark). With `FEATURE_E2E_MODE=false`, asserts the probe endpoint returns 404 with no body. Verifies rule-26 constitutional behaviour.
- [X] T050 [P] [US4] Add `apps/control-plane/tests/unit/marketplace/test_parity_probe_rollback.py`. Mocks the synthetic-publish path to raise mid-flight; asserts the savepoint is rolled back and no synthetic agent persists. Verifies the production-safety claim in the contract.
- [X] T051 [P] [US4] Remove skip markers from `apps/control-plane/tests/integration/marketplace/test_no_consume_flag_visibility.py`. Asserts the result set, count, suggestion array, and analytics event are byte-identical between (a) fresh tenant with no flag and (b) same tenant after a matching public agent is published. Closes 099 T060.
- [X] T052 [P] [US4] Add `tests/e2e/suites/marketplace/test_non_leakage_parity.py` (CI parity test harness). Runs in the kind cluster against the live observability stack. Fails the build on any `parity_violation`. Per `contracts/non-leakage-parity-probe-rest.md` § CI integration.

**Checkpoint**: US4 fully functional. SC-004 information-non-leakage parity locked by CI test on every PR.

---

## Phase 7: User Story 5 — Forking a public agent into a private tenant (Priority: P2)

**Goal**: A consumer-flag-enabled Enterprise user can Fork a public agent into their tenant; provenance is recorded; the source's later updates do not auto-propagate but trigger a notification via UPD-044.

**Independent Test**: Per spec.md US5 Independent Test. Plus: T-CONSUMER-REGISTRATION confirms `MarketplaceFanoutConsumer` is registered (T009), and the source-update notification reaches the fork owner's inbox.

**Maps to**: FR-741.5, FR-741.6, FR-741.7. Success criterion: SC-006.

### Backend — fork closes 099 follow-ups

- [X] T053 [P] [US5] Update `RegistryService.fork_agent` in `apps/control-plane/src/platform/registry/service.py:1028` to resolve the consumer tenant's plan version and call `quota_enforcer.check_agent_publish` from UPD-047. Surface `quota_exceeded` (HTTP 402) on cap. Closes 099 NOTES Backend follow-up 1 (T066).
- [X] T054 [P] [US5] Update the same `fork_agent` to compare `mcp_server_refs` against the consumer tenant's tool registry (not surface them as-is). Returns `tool_dependencies_missing` only for tools NOT registered in the consumer's tenant. Closes 099 NOTES Backend follow-up 2 (T067).

### Frontend — fork button rewire + source-updated alert renderer

- [X] T055 [US5] Update `apps/web/app/(main)/marketplace/[namespace]/[name]/page.tsx` to mount `ForkAgentDialog` (committed in 099). Gate the Fork button visibility on the viewer's tenant having `consume_public_marketplace=true` (read from the auth store). Closes 099 NOTES Frontend follow-up 2 (T075).
- [X] T056 [P] [US5] Create `apps/web/components/features/marketplace/notifications/SourceUpdatedAlertRenderer.tsx`. Renders `marketplace.source_updated` as a notification card with deep-link to the source agent's detail page. Body explicitly states "this fork has NOT been auto-updated." Closes 099 NOTES Frontend follow-up 5 (T076).
- [X] T057 [P] [US5] Update `apps/web/lib/marketplace/notifications.ts` alert-type-to-renderer map to register `SourceUpdatedAlertRenderer` for `marketplace.source_updated`. Depends on T056.

### Tests — US5

- [X] T058 [P] [US5] Remove skip markers from `apps/control-plane/tests/integration/marketplace/test_fork_lifecycle.py`. End-to-end: fork creation, provenance check, edit isolation, source-update fan-out reaches fork-owner inbox. Closes 099 T064–T069.
- [X] T059 [P] [US5] Add `apps/control-plane/tests/integration/marketplace/test_fork_quota_enforcement.py` (under `integration_live` mark). Asserts a fork attempt by an Acme user whose plan is at the agent-publish cap returns HTTP 402 with code `quota_exceeded`. Verifies T053.
- [X] T060 [P] [US5] Add `apps/control-plane/tests/integration/marketplace/test_fork_tool_dependency_check.py` (under `integration_live` mark). Asserts a fork attempt for a public agent whose `mcp_server_refs` include a tool not registered in the consumer's tenant returns the missing tool name in the response body. Verifies T054.
- [X] T061 [P] [US5] Add `apps/control-plane/tests/integration/marketplace/test_marketplace_fanout_consumer_registered.py` (under `integration_live` mark). On worker startup, asserts `MarketplaceFanoutConsumer.is_running()` is true. Locks T009 against regression.
- [X] T062 [P] [US5] Add `apps/web/tests/e2e/marketplace/fork-and-source-updated.spec.ts` (Playwright). Drives a fork, then triggers a source approval, then asserts the alert appears in the fork owner's inbox with the no-auto-update sentence. Closes 099 T050.

**Checkpoint**: US5 fully functional. Fork quota and tool-dependency cross-check work. Source updates reach fork owners via UPD-044 channel.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, dashboards, axe accessibility, and the residual CI gates.

- [X] T063 [P] Update `docs/saas/marketplace-scope.md` with two new sections: "Reviewer Assignment Workflow" (documents the assign/unassign UI + audit semantics) and "Consume-Flag Opt-In Walkthrough" (documents the platform-staff toggle + the user-visible badge). Per constitutional rule 36.
- [X] T064 [P] Add an axe-core accessibility check to `apps/web/tests/e2e/accessibility/marketplace.spec.ts` covering the queue page, the assignment dialog, the publish flow, and the fork dialog. Per constitutional rule 28 + 41.
- [X] T065 [P] Verify SC-007 panel (queue listing p95 < 2 s) and SC-008 panel (rejection notification p95 < 60 s) on the Grafana marketplace dashboard render correctly with synthetic data injected via `make seed-e2e`.
- [X] T066 Run `pytest apps/control-plane/tests/integration/marketplace/ -m integration_live` and confirm all 18 previously-scaffolded tests now pass (plus the 7 new tests added by this refresh). Document any flakes in `specs/102-marketplace-scope/NOTES.md`.
- [X] T067 [P] Run `pnpm --filter @musematic/web test:a11y` and `pnpm --filter @musematic/web e2e -- --grep marketplace` to confirm frontend accessibility and e2e coverage is green.
- [X] T068 [P] Run `mypy --strict apps/control-plane/src/platform/marketplace/` and `mypy --strict apps/control-plane/src/platform/registry/` to confirm the new code passes strict typing.
- [X] T069 [P] Run `make migrate-check` after Alembic migration 109 is applied to confirm `109_marketplace_reviewer_assignment` is the new head with no chain conflicts.
- [X] T070 Append a `## Refresh-Pass Summary` section to `specs/102-marketplace-scope/NOTES.md` enumerating every 099 NOTES item closed (Backend follow-ups 1–5, Frontend follow-ups 1–6) and every new behaviour added (self-review guard, assignment, parity probe, cost-attribution lock).

---

## Dependencies

```text
Phase 1 (Setup) ─┐
                 ├─► Phase 2 (Foundational, blocks everything below)
                 │      │
                 │      ├─► Phase 3 (US1, P1) — MVP
                 │      ├─► Phase 4 (US2, P1) — independent of US1
                 │      ├─► Phase 5 (US3, P2) — independent of US1/US2; uses Phase 2's consumer registration
                 │      ├─► Phase 6 (US4, P2) — independent
                 │      └─► Phase 7 (US5, P2) — depends on Phase 2 T009 (consumer registration); otherwise independent
                 │
                 └─► Phase 8 (Polish) — runs after all user-story phases pass
```

### Inter-task dependencies (within phases)

- T012, T014, T017 depend on T011 (the helper) and T015 (the assign methods) where indicated.
- T016 depends on T015 + T013 + T014.
- T019 depends on T015 and T005.
- T023 depends on T021, T022.
- T025 depends on T021, T024.
- T045 depends on T044.
- T057 depends on T056.

### Cross-phase dependencies

- All Phase 3–7 tests (T028, T029, T030, T031, T032, T035, T036, T041, T042, T048, T049, T051, T058, T059, T060, T061, T062) depend on Phase 2 T010 (live-DB+Kafka fixture).
- T053, T054 close 099 backend follow-ups but are otherwise independent of other US5 tasks (T055, T056, T057 are frontend).

---

## Parallel Execution Examples

### Within Phase 2 (after T004 — migration applied)

```bash
# T005, T006, T007, T008 can run in parallel:
$ Task: "T005 — add column to AgentProfile"
$ Task: "T006 — add 4 exception classes"
$ Task: "T007 — add 2 Kafka event types"
$ Task: "T008 — add audit kind constant"
```

### Within Phase 3 (US1)

```bash
# Backend self-review guard cluster: T011 (helper) → T012 (wire into 3 methods)
# In parallel: T013 (FastAPI dependency) — different file
# In parallel: T015 (assign methods) — same file as T012, sequence them
# In parallel: T018 (schemas), T020 (notifications), T021 (frontend), T022 (frontend), T024 (hooks)
$ Task: "T011 — _ensure_not_self_review helper"
$ Task: "T013 [P] — FastAPI dependency"
$ Task: "T018 [P] — Pydantic schemas"
$ Task: "T020 [P] — UPD-042 notification wiring"
$ Task: "T021 [P] — ReviewQueueAssignmentControls component"
$ Task: "T022 [P] — ReviewQueueFilterChips component"
$ Task: "T024 [P] — TanStack Query mutation hooks"
```

### Within Phase 6 (US4)

```bash
# T044 (probe service) → T045 (route) sequenced
# In parallel: T046 (schemas), T048–T052 (tests, all different files)
$ Task: "T044 — MarketplaceParityProbe service"
$ Task: "T046 [P] — parity probe schemas"
$ Task: "T048 [P] — non-leakage parity integration test"
$ Task: "T049 [P] — 404-in-production probe test"
$ Task: "T050 [P] — savepoint rollback unit test"
```

### Within Phase 7 (US5)

```bash
# Backend T053, T054 are different concerns in the same fork_agent method — sequence them
# In parallel: T056 (alert renderer), T057 (registration), T059, T060, T061, T062 (tests)
$ Task: "T053 — fork quota integration"
$ Task: "T056 [P] — SourceUpdatedAlertRenderer"
$ Task: "T059 [P] — fork quota integration test"
$ Task: "T060 [P] — fork tool-dependency cross-check test"
$ Task: "T061 [P] — consumer-registered regression test"
```

---

## Implementation Strategy

### MVP scope

**Phase 3 (US1) is the MVP.** It delivers the full publish → assign → claim → approve/reject → notify cycle with self-review prevention, which is the core value proposition of the refresh pass and the gate for SC-001/007/008.

### Incremental delivery

Recommended PR slicing:

1. **PR 1** (Phase 1 + Phase 2): Setup + Foundational. Ships migration 109, model update, exception/event/audit definitions, consumer registration, integration fixture. Reviewable as a small, self-contained schema + plumbing change.
2. **PR 2** (Phase 3, US1): MVP. Self-review guard, reviewer assignment endpoints + UI, rejection notifications via UPD-042, publish-page rewire. Adds the full backend + frontend behaviour for the headline user story.
3. **PR 3** (Phase 4, US2): Regression locks for the 099 three-layer Enterprise refusal. Smallest PR; pure test-coverage closeout.
4. **PR 4** (Phase 5, US3): Visibility surfacing (badge, edit-hide), feature-flag toggle UI, cost-attribution regression lock.
5. **PR 5** (Phase 6, US4): Parity probe service + endpoint + CI test corpus. Feature-flagged dev-only path; production-safety unit test.
6. **PR 6** (Phase 7, US5): Fork quota integration, tool-dependency cross-check, source-updated alert renderer.
7. **PR 7** (Phase 8): Polish — docs, axe, dashboards, mypy strict.

Each PR ends with a passing CI run including the integration suite. No PR depends on a later PR's behaviour. PRs 3–6 can ship in any order after PR 2.

---

## Total task count

- **Phase 1 Setup**: 3 tasks (T001–T003)
- **Phase 2 Foundational**: 7 tasks (T004–T010)
- **Phase 3 US1**: 24 tasks (T011–T034)
- **Phase 4 US2**: 3 tasks (T035–T037)
- **Phase 5 US3**: 6 tasks (T038–T043)
- **Phase 6 US4**: 9 tasks (T044–T052)
- **Phase 7 US5**: 10 tasks (T053–T062)
- **Phase 8 Polish**: 8 tasks (T063–T070)

**Total**: **70 tasks**.

### Independent test criteria summary

| Story | Priority | Independent test |
|---|---|---|
| US1 | P1 | Publish → assign → claim → approve flow plus reject notification plus self-review 403; verified by T028, T029, T030, T031, T032 |
| US2 | P1 | Three-layer Enterprise refusal (UI/API/DB); verified by T035, T036, T037 |
| US3 | P2 | Merged result set + badge + cost attribution to consumer; verified by T041, T042, T043 |
| US4 | P2 | Parity probe returns no violation across 5 canonical terms; verified by T048, T049, T051, T052 |
| US5 | P2 | Fork → quota check → tool check → source-update notification; verified by T058, T059, T060, T061, T062 |

### Format validation

✅ All 70 tasks follow the strict `- [ ] [TaskID] [P?] [Story?] Description with file path` format.
✅ Setup phase (T001–T003) and Foundational phase (T004–T010) have **no** Story labels.
✅ Phase 3–7 user-story tasks (T011–T062) all carry `[US1]`–`[US5]` labels.
✅ Phase 8 polish (T063–T070) has **no** Story labels.
✅ Every task has an exact file path or absolute action.
