# Tasks: UPD-043 — Workspace Owner Workbench and Connector Self-Service

**Feature**: 093-workspace-owner-workbench
**Branch**: `093-workspace-owner-workbench`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Workspace owner reviews their workspace via `/workspaces/{id}` dashboard with 7 cards (goals, executions, agents, budget gauge, quotas, tags, DLP) scoped to the workspace.
- **US2 (P1)** — Workspace owner manages members via `/members` page; ownership transfer 2PA-gated per Rule 33 (greenfield 2PA primitive in this feature).
- **US3 (P1)** — Workspace owner configures workspace-scoped connectors via `/connectors` 5-step setup wizard (Slack/Telegram/Email/Webhook); test-connectivity NEVER sends user-visible messages per FR-662.
- **US4 (P2)** — Workspace owner sets budget + hard cap per FR-503 reuse from UPD-079.
- **US5 (P2)** — Admin configures LDAP/OIDC/SCIM IBOR connector via extended `/admin/settings?tab=ibor` with test-connection diagnostic + attribute-mapping wizard + sync-history.
- **US6 (P3)** — Workspace owner explores visibility graph via `/visibility` page (XYFlow + Dagre — NOT Cytoscape per spec correction §5).

Independent-test discipline: every US MUST be verifiable in isolation. US1 = workspace with seeded data + dashboard ≤ 3s + scoped query (other-workspace 403). US2 = invite + role change + transfer-ownership with 2PA double-audit. US3 = 5-step wizard + test-connectivity (no user-visible message) + Vault-stored secret + activity panel + rotation. US4 = budget save + threshold alerts + hard-cap block. US5 = LDAP wizard + stepped diagnostic + sync-now + sync-history. US6 = ≤ 500-node graph in ≤ 1s + zero-trust default visualization.

**Wave-18 sub-division** (per plan.md "Effort & Wave"):
- W18.0 — Setup: T001-T004
- W18A — Track A Backend additions (depends on UPD-040 + UPD-041 + UPD-042 / Waves 15-17): T005-T044
- W18B — Track B Frontend pages (depends on Track A schemas): T045-T093
- W18C — Track C E2E + journey: T094-T106
- W18D — Cross-cutting verification (Rule 31 + Rule 33 invariants + audit emission): T107-T111
- W18E — SC verification + documentation polish: T112-T125

---

## Phase 1: Setup

- [X] T001 [W18.0] Verify the on-disk repo state per plan.md "Phase 0 — Research" + spec.md scope-discipline section: confirm UPD-040 (Wave 15) + UPD-041 (Wave 16) + UPD-042 (Wave 17) are on `main`; confirm `apps/control-plane/src/platform/workspaces/router.py:50-346` has 18 existing endpoints (workspace CRUD + members + settings + visibility + goals + governance-chain); confirm `apps/control-plane/src/platform/connectors/router.py:82-237` has 14 workspace-scoped endpoints (CRUD + health-check + routes + deliveries + dead-letter); confirm `apps/control-plane/src/platform/connectors/models.py:89-92` has `ConnectorInstance.workspace_id NOT NULL` (per spec correction §3); confirm `apps/web/components/features/admin/AdminSettingsPanel.tsx:16-39` tab array exists with 7 tabs; confirm NO `/workspaces/[id]/*` UI route exists today; confirm NO existing 2PA implementation per Rule 33 + spec correction §12; confirm `package.json` has `@xyflow/react` + `@dagrejs/dagre`, NO Cytoscape; confirm migration sequence at `070_user_self_service_extensions.py` so `071` is the next slot per research R11. Document inventory in `specs/093-workspace-owner-workbench/contracts/repo-inventory.md` (NEW file). If any of UPD-040/041/042 is NOT merged, BLOCK UPD-043 implementation.
- [X] T002 [P] [W18.0] Verify the migration sequence per research R11: confirm `apps/control-plane/migrations/versions/` highest-numbered migration is `070_*`; if UPD-040/041/042 own additional slots beyond 070, document the actual next sequence in `specs/093-workspace-owner-workbench/contracts/migration-sequence.md` (NEW file). Default `071`; may shift to `072+`.
- [X] T003 [P] [W18.0] Verify the constitutional anchors per plan.md Constitutional Anchors table: open `.specify/memory/constitution.md` and confirm Rule 9 (PII audit), Rule 10 (vault credentials), Rule 30 (admin role gates), **Rule 33 lines 213-216 (2PA enforced server-side — THE canonical anchor for this feature)**, Rule 41 (AA accessibility), Rule 45 (lines 258-262 — every user-facing backend capability has UI), Rule 47 (workspace vs platform scope distinction). If any rule has been renumbered or rewritten, escalate via spec amendment. Document confirmation in `specs/093-workspace-owner-workbench/contracts/constitution-confirmation.md` (NEW file).
- [X] T004 [P] [W18.0] Cross-feature coordination check per plan.md "Cross-feature dependency map": confirm UPD-040 SecretProvider on `main`; confirm UPD-077 multi-channel notifications on `main` (used for member invitation emails); confirm UPD-079 cost_governance on `main` (budget gauge); confirm UPD-033 tagging on `main`; confirm UPD-076/078 DLP on `main`; confirm UPD-039 (Documentation) status — if landed, runbooks land in `docs/operator-guide/`; if not, runbooks live in feature `contracts/`. Document in `specs/093-workspace-owner-workbench/contracts/cross-feature-deps.md` (NEW file).

---

## Phase 2: Track A — Backend Additions

**Story goal**: Alembic migration `071` (3 new JSONB columns on `WorkspaceSettings` + 1 NEW `two_person_approval_challenges` table); 8 net-new endpoints (workspace summary + transfer-ownership + connector test-connectivity + 3 IBOR + 3 2PA); foundational 2PA primitive as NEW BC; 4 connector dry-run methods; 9 new audit-event types. Honors Rule 9 + Rule 10 + Rule 30 + Rule 33 + Rule 45 + Rule 47.

### Alembic migration + model extensions

- [X] T005 [W18A] [US1, US3, US4] Create `apps/control-plane/migrations/versions/071_workspace_owner_workbench.py` (or verified next-sequence number from T002) per plan.md design D1 + D2: 3 ALTER TABLE statements adding JSONB columns to `workspaces_settings` per spec correction §1 — `quota_config: JSONB DEFAULT '{}'`, `dlp_rules: JSONB DEFAULT '{}'`, `residency_config: JSONB DEFAULT '{}'`. CREATE TABLE `two_person_approval_challenges` per spec correction §12 + design D2: columns `id` UUID PK, `action_type` ENUM, `action_payload` JSONB NOT NULL, `initiator_id` UUID FK users.id, `co_signer_id` UUID FK users.id NULL, `status` ENUM `pending`/`approved`/`consumed`/`expired` DEFAULT 'pending', `created_at` timestamptz, `expires_at` timestamptz NOT NULL, `approved_at` timestamptz NULL, `consumed_at` timestamptz NULL. Reversible downgrade.
- [ ] T006 [W18A] Run `alembic upgrade head` locally; verify migration applies cleanly + downgrade -1 removes 3 columns + 1 table without data loss in existing 5 ARRAY + 1 JSONB columns of `workspaces_settings`.
- [X] T007 [W18A] [US1, US3, US4] Modify `apps/control-plane/src/platform/workspaces/models.py:208-248` per plan.md design D1: add 3 new mapped columns on `WorkspaceSettings` — `quota_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)`, `dlp_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)`, `residency_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)`. Preserve the existing 5 ARRAY + 1 `cost_budget` JSONB unchanged.

### `two_person_approval/` BC (foundational greenfield primitive)

- [X] T008 [W18A] [US2] Create `apps/control-plane/src/platform/two_person_approval/__init__.py` (NEW empty module).
- [X] T009 [W18A] [US2] Create `apps/control-plane/src/platform/two_person_approval/models.py` (NEW per plan.md design D2 + D3): `class TwoPersonApprovalChallenge(Base, UUIDMixin, TimestampMixin)` with `action_type: Mapped[ActionType]` (extensible enum — initial value `workspace_transfer_ownership`), `action_payload: Mapped[dict[str, Any]]` (JSONB — frozen at creation), `initiator_id`, `co_signer_id` (nullable), `status: Mapped[ChallengeStatus]` enum, `expires_at`, `approved_at`, `consumed_at`.
- [X] T010 [W18A] [US2] Create `apps/control-plane/src/platform/two_person_approval/schemas.py` (NEW): Pydantic schemas — `CreateChallengeRequest(action_type, action_payload)`, `ChallengeResponse(id, action_type, status, created_at, expires_at, ...)`, `ApproveChallengeResponse`, `ConsumeChallengeResponse(action_result: dict)`. Per Rule 33 — the action_payload is FROZEN; consumers receive only the challenge metadata, not the raw payload.
- [X] T011 [W18A] [US2] Create `apps/control-plane/src/platform/two_person_approval/service.py` (NEW per plan.md design D2 + D4): `TwoPersonApprovalService` with 3 methods: `create_challenge(initiator_id, action_type, action_payload, ttl_seconds=300) -> ChallengeResponse`; `approve_challenge(challenge_id, co_signer_id) -> ChallengeResponse` (validates `co_signer_id != initiator_id` per design D4 + Rule 33; transitions `pending → approved` atomically via `SELECT FOR UPDATE`); `consume_challenge(challenge_id, requester_id) -> dict` (validates `status == approved` AND `requester_id == initiator_id`; transitions `approved → consumed` atomically; returns the FROZEN `action_payload` for the caller to execute). Redis hash mirror at `2pa:challenge:{id}` with TTL=expires_at-now for fast lookup + auto-expiry.
- [X] T012 [W18A] [US2] Create `apps/control-plane/src/platform/two_person_approval/router.py` (NEW per FR-561 + Rule 33): 3 endpoints — `POST /api/v1/2pa/challenges` (initiator creates), `POST /api/v1/2pa/challenges/{id}/approve` (admin co-signer approves; depends on `_require_platform_admin` per Rule 30), `POST /api/v1/2pa/challenges/{id}/consume` (initiator consumes after approval). Each emits audit-chain entry per Rule 9.
- [X] T013 [W18A] Modify `apps/control-plane/src/platform/main.py`: register `two_pa_router` via `app.include_router(two_pa_router, prefix="/api/v1")` AFTER the existing workspaces router registration.
- [X] T014 [W18A] [US2] Author `apps/control-plane/tests/two_person_approval/test_router.py` (NEW pytest test file): ~12 cases covering 3 endpoints — happy path, `co_signer_id == initiator_id` rejected per design D4, expired challenge rejected, double-consume rejected, non-admin approve rejected per Rule 30.
- [X] T015 [W18A] [US2] Author `apps/control-plane/tests/two_person_approval/test_service.py` (NEW): ~10 cases covering atomic state transitions (pending→approved→consumed only valid path), TTL expiry (Redis mirror + DB cleanup), TOCTOU prevention (consume executes the FROZEN action_payload, NOT a client-resubmitted one).

### Workspace router extensions

- [X] T016 [W18A] [US1] Add `GET /api/v1/workspaces/{workspace_id}/summary` endpoint to `apps/control-plane/src/platform/workspaces/router.py` per FR-658: handler `async def get_workspace_summary(workspace_id, current_user, workspaces_service)`; calls `workspaces_service.get_summary(workspace_id, _requester_id(current_user))` per design D11 (Redis-cached 30s).
- [X] T017 [W18A] [US1] Modify `apps/control-plane/src/platform/workspaces/service.py`: add `async def get_summary(workspace_id, requester_id) -> WorkspaceSummaryResponse` method aggregating goals + executions + agents + budget gauge (UPD-079 reuse per research R13) + quota usage (NEW `quota_config` JSONB) + tag summary (UPD-033 reuse per research R12) + DLP violations count (UPD-076/078 reuse) + recent audit activity. Cache result in Redis at `workspace:summary:{workspace_id}` TTL=30s per design D11; invalidate on workspace state change via existing audit-event Kafka subscription.
- [X] T018 [W18A] [US2] Add `POST /api/v1/workspaces/{workspace_id}/transfer-ownership` endpoint per FR-659 + Rule 33: handler accepts `TransferOwnershipRequest(new_owner_id)`; creates a 2PA challenge via `two_pa_service.create_challenge(initiator_id=current_user.id, action_type='workspace_transfer_ownership', action_payload={workspace_id, new_owner_id})`; returns the challenge ID for the frontend to display. Emits `auth.workspace.transfer_initiated` audit entry per spec correction §10.
- [X] T019 [W18A] [US2] Add internal handler in `workspaces/service.py`: `async def commit_ownership_transfer(challenge_id, requester_id) -> WorkspaceResponse`. This is invoked by the 2PA `consume` endpoint's action handler registry. Validates `requester_id == challenge.initiator_id == current_owner_id`; swaps `Workspace.owner_id = new_owner_id`; creates new `Membership` row for previous owner (downgrades to `admin` role); emits `auth.workspace.transfer_committed` audit entry.
- [X] T020 [W18A] [US2] Register the `workspace_transfer_ownership` action handler in `two_person_approval/service.py`: `consume_challenge` dispatches by `action_type` to the appropriate handler — `workspace_transfer_ownership` calls `workspaces_service.commit_ownership_transfer(challenge_id, requester_id)`. Extensible for future destructive ops per design D3.
- [X] T021 [W18A] [US1, US3, US4] Modify `apps/control-plane/src/platform/workspaces/schemas.py` per plan.md "Source Code" section: add 6 new schemas — `WorkspaceSummaryResponse(active_goals, executions_in_flight, agent_count, budget, quotas, tags, dlp_violations, recent_activity)`, `TransferOwnershipRequest(new_owner_id)`, `WorkspaceQuotaConfig`, `WorkspaceDLPRules`, `WorkspaceResidencyConfig`, `WorkspaceSummaryCardData`.

### Connector router extensions + dry-run methods

- [X] T022 [W18A] [US3] Add `POST /api/v1/workspaces/{workspace_id}/connectors/{connector_instance_id}/test-connectivity` endpoint to `apps/control-plane/src/platform/connectors/router.py` per FR-662 + spec correction §6 + design D5 + D6: handler `async def test_connectivity(workspace_id, connector_instance_id, candidate_config: TestConnectivityRequest, current_user, connectors_service) -> TestConnectivityResponse`; calls `connectors_service.test_connectivity(workspace_id, connector_instance_id, candidate_config)`. The result is NOT persisted to `outbound_deliveries` per design D6.
- [X] T023 [W18A] [US3] Modify `apps/control-plane/src/platform/connectors/service.py`: add `async def test_connectivity(workspace_id, connector_instance_id, candidate_config) -> TestConnectivityResponse` method that resolves the connector instance + invokes the connector implementation's NEW `test_connectivity()` method per design D5.
- [X] T024 [W18A] [US3] Add `async def test_connectivity(self, config, credential_refs) -> TestResult` method to `apps/control-plane/src/platform/connectors/implementations/slack.py` per research R10 + design D5 + D6: uses Slack `auth.test` API (validates token without sending messages); returns `TestResult(success: bool, diagnostic: str, latency_ms: float)`.
- [X] T025 [P] [W18A] [US3] Add `test_connectivity()` method to `connectors/implementations/telegram.py` per research R10: uses Telegram `getMe` API (validates bot token).
- [X] T026 [P] [W18A] [US3] Add `test_connectivity()` method to `connectors/implementations/email.py`: uses SMTP/IMAP NOOP commands (validates auth without sending email).
- [X] T027 [P] [W18A] [US3] Add `test_connectivity()` method to `connectors/implementations/webhook.py`: uses HEAD request to webhook URL (validates URL reachable + HMAC config without POST).
- [X] T028 [W18A] [US3] Author `apps/control-plane/tests/connectors/test_test_connectivity.py` (NEW pytest test file): ~16 cases covering 4 connector dry-run methods — Slack auth.test success/failure, Telegram getMe, Email NOOP, Webhook HEAD. Each verifies NO `outbound_deliveries` row created during the test (per design D6 + spec edge case).

### IBOR admin extensions

- [X] T029 [W18A] [US5] Add 3 NEW IBOR admin endpoints to `apps/control-plane/src/platform/auth/router.py` per FR-664 + spec correction §13: `POST /api/v1/auth/ibor/connectors/{connector_id}/test-connection`, `POST /api/v1/auth/ibor/connectors/{connector_id}/sync-now`, `GET /api/v1/auth/ibor/connectors/{connector_id}/sync-history`. Each calls `_require_platform_admin(current_user)` per Rule 30.
- [X] T030 [W18A] [US5] Modify `apps/control-plane/src/platform/auth/ibor_service.py` per research R3 + plan.md design D9 + D10: add 3 NEW methods — `test_connection(connector_id) -> TestConnectionResponse` returning stepped diagnostic per design D10 (`[{step: "dns_lookup", status: "success", duration_ms: 45}, ...]` covering DNS + TCP connect + TLS handshake + LDAP bind + sample query); `sync_now(connector_id) -> SyncRunResponse` (delegates to existing `IBORSyncService.trigger_sync`); `get_sync_history(connector_id, limit, cursor) -> list[IBORSyncRunResponse]` (cursor pagination via `(timestamp DESC, id DESC)` exposing existing `list_sync_runs`).
- [X] T031 [W18A] [US5] Author `apps/control-plane/tests/auth/test_ibor_admin_endpoints.py` (NEW pytest test file): ~12 cases covering 3 new endpoints — happy path + each step of stepped diagnostic + non-admin rejected per Rule 30 + sync-history pagination.

### Pydantic schemas + audit events

- [X] T032 [W18A] [US3, US5] Add NEW Pydantic schemas to `connectors/schemas.py` + `auth/schemas.py`: `TestConnectivityRequest`, `TestConnectivityResponse`, `TestResult` (uniform per design D5), `TestConnectionResponse(steps: list[StepResult])`, `StepResult(step: str, status: str, duration_ms: int, error: str | None)`, `SyncRunResponse`, `IBORSyncHistoryResponse`.
- [X] T033 [W18A] Wire 9 new audit-event types per spec correction §10 across the relevant services: `auth.workspace.member_added`, `auth.workspace.member_removed`, `auth.workspace.role_changed`, `auth.workspace.transfer_initiated`, `auth.workspace.transfer_committed`, `auth.workspace.budget_updated`, `auth.workspace.quota_updated`, `auth.workspace.dlp_rules_updated`, `auth.workspace.connector_added`, `auth.workspace.connector_removed`. Each follows the existing dual-emission pattern (`repository.create_audit_entry` + `publish_auth_event`).

### Track A integration tests

- [X] T034 [W18A] [US1] Author `apps/control-plane/tests/workspaces/test_summary_endpoint.py` (NEW pytest test file): ~8 cases — aggregator response shape, Redis cache hit on second call, cache invalidation on workspace state change, scope enforcement (other-workspace 403), permission check.
- [X] T035 [W18A] [US2] Author `apps/control-plane/tests/workspaces/test_transfer_ownership.py` (NEW pytest test file): ~10 cases — initiate-transfer creates 2PA challenge, transfer-initiated audit emitted, consume-challenge swaps owner_id, transfer-committed audit emitted, prior owner downgraded to admin role, same-actor approval rejected per design D4, expired challenge rejected, non-owner-initiator rejected.

**Checkpoint (end of Phase 2)**: `pytest apps/control-plane/tests/{two_person_approval,workspaces,connectors,auth}/` passes (~60 unit tests); the 8 new endpoints + 3 2PA endpoints + 4 dry-run methods + 9 audit-event types are wired correctly; the migration is reversible; the 2PA primitive enforces atomic state transitions + same-actor refusal + 5-minute TTL + TOCTOU prevention.

---

## Phase 3: Track B — Frontend Pages

**Story goal**: 8 NEW Next.js workspace-scoped pages + 3 admin tab extensions per FR-658 through FR-665 + Rule 45. ~30 sub-components. i18n × 6 locales. axe-core AA per Rule 41.

### Shared scaffolding

- [X] T036 [W18B] [US1, US2, US3, US4, US5, US6] Create `apps/web/components/layout/WorkspaceOwnerLayout.tsx` (NEW ~150 lines): sidebar nav for `/workspaces/[id]/*` route group; renders 7 nav items (Dashboard, Members, Settings, Connectors, Quotas, Tags, Visibility); reads `workspaceId` from `useParams()`.
- [X] T037 [W18B] Create `apps/web/lib/api/workspace-owner.ts` (NEW): fetch wrappers for 8 new endpoints (workspace summary, transfer-ownership, connector test-connectivity, 3 IBOR endpoints, 3 2PA endpoints).
- [X] T038 [W18B] Create `apps/web/lib/schemas/workspace-owner.ts` (NEW): Zod schemas mirroring backend Pydantic schemas from Track A T032 + T021.
- [X] T039 [P] [W18B] Create `apps/web/lib/hooks/use-workspace-summary.ts` (NEW): TanStack Query hook for `GET /workspaces/{id}/summary`.
- [X] T040 [P] [W18B] Create `apps/web/lib/hooks/use-2pa-challenge.ts` (NEW): hooks `useCreateChallenge()`, `useChallenge(id)`, `useConsumeChallenge()` for 3 2PA endpoints.
- [X] T041 [P] [W18B] Create `apps/web/lib/hooks/use-connector-test-connectivity.ts` (NEW).
- [X] T042 [P] [W18B] Create `apps/web/lib/hooks/use-ibor-admin.ts` (NEW): hooks for test-connection / sync-now / sync-history.
- [X] T043 [P] [W18B] Create `apps/web/lib/hooks/use-workspace-members.ts` (NEW): hooks for existing `/members` endpoints + transfer-ownership.

### Workspaces list + dashboard (US1)

- [X] T044 [W18B] [US1] Create `apps/web/app/(main)/workspaces/page.tsx` (NEW ~200 lines): workspaces list page; lists workspaces user owns or belongs to; reuses existing `GET /workspaces` endpoint.
- [X] T045 [W18B] [US1] Create `apps/web/app/(main)/workspaces/[id]/page.tsx` (NEW ~250 lines): dashboard with 7 cards per FR-658. Reads from new `GET /workspaces/{id}/summary` endpoint via T039 hook.
- [X] T046 [W18B] [US1] Create 7 dashboard card sub-components in `apps/web/app/(main)/workspaces/[id]/_components/`: `ActiveGoalsCard.tsx`, `ExecutionsInFlightCard.tsx`, `AgentCountCard.tsx`, `BudgetGaugeCard.tsx` (UPD-079 reuse per research R13), `QuotaUsageBarsCard.tsx`, `TagSummaryCard.tsx` (UPD-033 reuse per research R12), `DLPViolationsCountCard.tsx` (UPD-076/078 reuse). Each ~80 lines.
- [X] T047 [P] [W18B] [US1] Create `apps/web/app/(main)/workspaces/[id]/_components/RecentActivityFeed.tsx` (NEW ~150 lines): chronological feed of last 10 audit entries scoped to workspace; reads via the existing audit chain query API extended in UPD-042 task T014.

### Members page (US2)

- [X] T048 [W18B] [US2] Create `apps/web/app/(main)/workspaces/[id]/members/page.tsx` (NEW ~250 lines): members table with role + joined-date + recent-activity link; invite + role change + remove + transfer-ownership actions. Reads from existing `GET /workspaces/{id}/members` endpoint.
- [X] T049 [W18B] [US2] Create `apps/web/app/(main)/workspaces/[id]/members/_components/InviteMemberDialog.tsx` (NEW ~150 lines): shadcn Dialog with email input + role select (4 options per WorkspaceRole enum) + role descriptions; calls existing `POST /workspaces/{id}/members`.
- [X] T050 [W18B] [US2] Create `apps/web/app/(main)/workspaces/[id]/members/_components/TransferOwnershipDialog.tsx` (NEW ~200 lines) per Rule 33 + spec correction §12: 3-step flow — (1) Initiate (calls `POST /workspaces/{id}/transfer-ownership` per FR-659 — initiator creates 2PA challenge); (2) Wait for co-signer approval (polls `GET /2pa/challenges/{id}` via T040 hook every 2s); (3) Consume (calls `POST /2pa/challenges/{id}/consume`). Display challenge expiry countdown.

### Settings page (US4)

- [X] T051 [W18B] [US4] Create `apps/web/app/(main)/workspaces/[id]/settings/page.tsx` (NEW ~250 lines): tabs for 4 sub-domains per FR-660 — Budget, Quotas, DLP, Residency. Reads + writes via existing `GET/PATCH /workspaces/{id}/settings`.
- [X] T052 [P] [W18B] [US4] Create `apps/web/app/(main)/workspaces/[id]/settings/_components/BudgetForm.tsx` (NEW ~150 lines): writes to existing `cost_budget` JSONB; soft thresholds + hard cap + admin-override visibility per UPD-079 + FR-503.
- [X] T053 [P] [W18B] [US1] Create `apps/web/app/(main)/workspaces/[id]/settings/_components/QuotaConfigForm.tsx` (NEW ~150 lines): writes to NEW `quota_config` JSONB per design D1; per-resource controls (agents/fleets/executions/storage).
- [X] T054 [P] [W18B] [US1] Create `apps/web/app/(main)/workspaces/[id]/settings/_components/DLPRulesForm.tsx` (NEW ~150 lines): writes to NEW `dlp_rules` JSONB; extends UPD-076/078 globals.
- [X] T055 [P] [W18B] [US1] Create `apps/web/app/(main)/workspaces/[id]/settings/_components/ResidencyForm.tsx` (NEW ~120 lines): writes to NEW `residency_config` JSONB.

### Connectors pages (US3)

- [X] T056 [W18B] [US3] Create `apps/web/app/(main)/workspaces/[id]/connectors/page.tsx` (NEW ~200 lines) per FR-661: lists existing workspace-scoped connectors via existing `GET /workspaces/{id}/connectors` endpoint; renders "workspace-owned" badge per spec correction §3 + Rule 47; "Add connector" button opens type-picker modal.
- [X] T057 [W18B] [US3] Create `apps/web/app/(main)/workspaces/[id]/connectors/[connectorId]/page.tsx` (NEW ~250 lines): connector detail with activity panel (T060) + rotate-secret action (T061).
- [X] T058 [W18B] [US3] Create `apps/web/app/(main)/workspaces/[id]/connectors/_components/ConnectorSetupWizard.tsx` (NEW ~400 lines) per FR-662: 5-step shadcn Stepper — (1) prerequisites check; (2) credentials; (3) test-connectivity (calls new `POST /test-connectivity` per FR-662 + spec correction §6); (4) scope (writes to existing `connector_routes` table per research R6); (5) activate.
- [X] T059 [P] [W18B] [US3] Create 4 connector-specific wizard step components: `SlackWizardSteps.tsx` (~150 lines), `TelegramWizardSteps.tsx` (~120 lines), `EmailWizardSteps.tsx` (~150 lines), `WebhookWizardSteps.tsx` (~120 lines). Each renders the connector-specific prerequisites + credentials inputs. Wizard composes the right step set based on connector type.
- [X] T060 [W18B] [US3] Create `apps/web/app/(main)/workspaces/[id]/connectors/_components/ConnectorActivityPanel.tsx` (NEW ~200 lines) per FR-663 + research R5: reads from existing `GET /workspaces/{wid}/connectors/{cid}/deliveries` endpoint (verified at `connectors/router.py:298-337`); renders 24h/7d delivery success/failure counts + recent failures with `error_history` JSONB drill-down.
- [X] T061 [W18B] [US3] Create `apps/web/app/(main)/workspaces/[id]/connectors/_components/RotateSecretDialog.tsx` (NEW ~150 lines) per Rule 44 + UPD-040 KV v2: write-only secret input; on submit, backend writes new Vault KV v2 version; returns 204 (no secret value in response per Rule 44).

### Quotas, tags, visibility pages (US1, US6)

- [X] T062 [P] [W18B] [US1] Create `apps/web/app/(main)/workspaces/[id]/quotas/page.tsx` (NEW ~200 lines): quota visualization + edit; reads/writes the NEW `quota_config` JSONB.
- [X] T063 [P] [W18B] [US1] Create `apps/web/app/(main)/workspaces/[id]/tags/page.tsx` (NEW ~180 lines): workspace tags page; reuses existing tagging API per research R12 — UI-only, no schema change.
- [X] T064 [W18B] [US6] Create `apps/web/app/(main)/workspaces/[id]/visibility/page.tsx` (NEW ~250 lines) per FR-665 + spec correction §5 + design D8: read-only visibility explorer. Tabs: Grants Given, Grants Received, Audit Trail.
- [X] T065 [W18B] [US6] Create `apps/web/app/(main)/workspaces/[id]/visibility/_components/VisibilityGraph.tsx` (NEW ~300 lines) per research R9: XYFlow + Dagre graph modeled on existing `HypothesisNetworkGraph.tsx` + `FleetTopologyGraph.tsx`. Builds nodes from `visibility_agents` + `visibility_tools` (response from existing `GET /workspaces/{id}/visibility` endpoint per research R8). Zero-trust default visualized as isolated node with "deny all" badge per spec edge case.
- [X] T066 [P] [W18B] [US6] Create `apps/web/app/(main)/workspaces/[id]/visibility/_components/GrantDetailPanel.tsx` (NEW ~150 lines): side panel rendering grant details (FQN pattern, source, created_at) when a graph edge is clicked.

### Admin tab extensions (US5)

- [X] T067 [W18B] [US5] Modify `apps/web/components/features/admin/AdminSettingsPanel.tsx:16-39` per plan.md design D12 + research R2: ADD 1 new tab entry `{ value: "workspaces", label: "Workspaces", icon: Building2, component: WorkspacesTab }` to the tabs array. Verify whether `ibor` is already in the array; if NOT, add `{ value: "ibor", label: "IBOR Connectors", icon: ServerCog, component: IBORTab }`. Existing 7 tabs preserved unchanged.
- [X] T068 [W18B] [US5] Create `apps/web/components/features/admin/_tabs/WorkspacesTab.tsx` (NEW ~250 lines): admin global view of all workspaces; reuses existing `GET /workspaces` endpoint with admin scope.
- [X] T069 [W18B] [US5] Create or extend `apps/web/components/features/admin/_tabs/IBORTab.tsx` (NEW ~250 lines if absent; modify if present) per FR-664: connectors list with status + Add wizard launcher.
- [X] T070 [W18B] [US5] Create `apps/web/components/features/admin/_tabs/_components/IBORConnectorWizard.tsx` (NEW ~400 lines) per FR-664: 7-step wizard — (1) connector type (LDAP/OIDC/SCIM); (2) connection params; (3) test-connection (calls NEW `POST /admin/ibor/{id}/test-connection` per spec correction §13; renders stepped diagnostic per design D10 with green/red indicators per step); (4) attribute mapping (T071); (5) sync schedule; (6) scope; (7) activate.
- [X] T071 [P] [W18B] [US5] Create `apps/web/components/features/admin/_tabs/_components/AttributeMappingWizard.tsx` (NEW ~250 lines): schema-aware source → platform field mapper; for LDAP, presets for Active Directory / OpenLDAP / FreeIPA per spec edge case (R-IBOR-VENDOR-VARIATION).
- [X] T072 [P] [W18B] [US5] Create `apps/web/components/features/admin/_tabs/_components/SyncHistoryDrillDown.tsx` (NEW ~200 lines) per FR-664: paginated table of sync runs from new `GET /admin/ibor/{id}/sync-history` endpoint; error rows link to Loki logs (UPD-084 integration).

### i18n integration

- [X] T073 [W18B] [US1, US2, US3, US4, US5, US6] Modify `apps/web/messages/en.json`: add ~80 new i18n keys under hierarchical namespaces — `workspaces.{dashboard,members,settings,connectors,quotas,tags,visibility}.*` + `admin.{ibor,workspaces}.*`. Reference these in all new TSX components via `useTranslations(...)` from `next-intl`.
- [X] T074 [P] [W18B] Modify `apps/web/messages/{de,es,fr,it,zh-CN,ja}.json`: copy English keys with TODO-translation markers per UPD-088's parity check; vendor translates per UPD-039 / FR-620.
- [X] T075 [P] [W18B] Run `pnpm test:i18n-parity` — verify all 6 locale catalogs have all new keys.

### Accessibility + frontend tests

- [X] T076 [W18B] Run axe-core scan on all 8 new pages + 3 admin tab extensions locally; verify zero AA violations per Rule 41 inheritance from UPD-083. Fix any violations introduced (likely candidates: dialog focus management, table keyboard nav, badge contrast, graph keyboard nav for visibility explorer).
- [X] T077 [W18B] Run `pnpm test`, `pnpm typecheck`, `pnpm lint` to verify all CI gates pass.

### Playwright E2E

- [X] T078 [W18B] [US1, US2, US3, US4, US5, US6] Create `apps/web/tests/e2e/workspace-owner-pages.spec.ts` (NEW Playwright test file): ~25 scenarios covering: (a) workspace list + dashboard (7 cards render); (b) members table + invite + role change + remove; (c) transfer-ownership 2PA flow (3 steps); (d) connector setup 5-step wizard for each of 4 types; (e) test-connectivity does NOT send user-visible message per User Story 3 acceptance scenario 3; (f) connector activity panel renders 24h/7d counts; (g) rotate-secret writes new Vault version (UPD-040 inheritance); (h) settings 4 sub-domains save correctly; (i) visibility graph renders ≤ 500 nodes in ≤ 1s per SC-014; (j) zero-trust default visualized as isolated node; (k) admin IBOR wizard 7 steps + stepped diagnostic + sync-now + sync-history.

**Checkpoint (end of Phase 3)**: 8 new pages + 3 admin tab extensions render correctly against the live Track A backend; `pnpm test`, `pnpm typecheck`, axe-core scan, i18n parity check all pass; Playwright E2E ~25 scenarios pass.

---

## Phase 4: Track C — E2E Suite + Journey Tests

**Story goal**: NEW `tests/e2e/suites/workspace_owner/` with 7 test files; J20 creation; J01 extension; matrix-CI inheritance from UPD-040.

### E2E suite scaffolding

- [X] T079 [W18C] [US1, US2, US3, US4, US5, US6] Create `tests/e2e/suites/workspace_owner/__init__.py` + `conftest.py` (NEW pytest fixtures): `workspace_with_seeded_data` (workspace + 3 active goals + 5 in-flight executions + 12 agents + tags + cost_budget at 60% consumption), `workspace_with_connectors` (workspace with 4 connector types pre-configured), `multi_member_workspace` (workspace with 4 members at different roles), `workspace_with_visibility_grants` (workspace with grants given + received).
- [X] T080 [W18C] [US1] Create `tests/e2e/suites/workspace_owner/test_dashboard_scoped.py` (NEW): 5 cases per User Story 1 — dashboard ≤ 3s, all 7 cards populated, scope enforcement (other-workspace 403), visibility-dependent metrics zero with tooltip when no grants, cache hit on second call.
- [X] T081 [P] [W18C] [US2] Create `tests/e2e/suites/workspace_owner/test_member_management.py` (NEW): 5 cases per User Story 2 — list + invite + role change + remove + audit emission verification.
- [X] T082 [P] [W18C] [US2] Create `tests/e2e/suites/workspace_owner/test_ownership_transfer_2pa.py` (NEW): 6 cases per User Story 2 + spec correction §12 + Rule 33 — initiate-transfer creates 2PA challenge, co-signer approval transitions challenge state, consume swaps owner_id, double-audit (initiated + committed), same-actor approval rejected per design D4, expired challenge rejected.
- [X] T083 [P] [W18C] [US3] Create `tests/e2e/suites/workspace_owner/test_workspace_connector_slack.py` (NEW): 5 cases per User Story 3 — 5-step wizard end-to-end, test-connectivity uses Slack auth.test (NO user-visible message per spec edge case), Vault path matches canonical UPD-040 scheme, activity panel reads from `outbound_deliveries`, rotate-secret writes new KV v2 version.
- [X] T084 [P] [W18C] [US3] Create `tests/e2e/suites/workspace_owner/test_workspace_connector_webhook.py` (NEW): 5 cases — webhook wizard, test-connectivity uses HEAD request (NOT POST), HMAC secret generation + storage in Vault.
- [X] T085 [P] [W18C] [US4] Create `tests/e2e/suites/workspace_owner/test_workspace_budget_enforcement.py` (NEW): 5 cases per User Story 4 — budget save + threshold alerts (50%, 80%) + hard cap block at 100% + admin override + forecast.
- [X] T086 [P] [W18C] [US6] Create `tests/e2e/suites/workspace_owner/test_visibility_explorer.py` (NEW): 4 cases per User Story 6 — graph rendering ≤ 500 nodes ≤ 1s, zero-trust default visualization, grants given vs received tabs, audit trail.

### Journey tests

- [X] T087 [W18C] [US1, US2, US3, US4, US6] Create `tests/e2e/journeys/test_j20_workspace_owner.py` (NEW per FR-666 + spec correction §11 + plan.md design D13). Modeled on J04 (verified at 31,924 bytes per spec phase research §17). ~250 lines covering 18 sequential `journey_step()` blocks: dashboard load → invite member → add Slack connector via 5-step wizard → test-connectivity → set budget → revoke session via UPD-042 self-service → DSR submission via UPD-042 → ownership transfer with 2PA → final state verification.
- [X] T088 [W18C] [US5] Modify `tests/e2e/journeys/test_j01_admin_bootstrap.py`: add 2 new `journey_step()` blocks covering the IBOR admin wizard — (1) "Admin opens `/admin/settings?tab=ibor`"; (2) "Admin runs LDAP test-connection + verifies stepped diagnostic + triggers sync-now + reviews sync-history". Total addition: ~30 lines.

### Matrix-CI integration

- [X] T089 [W18C] [US1, US2, US3, US4, US5, US6] Modify `.github/workflows/ci.yml`: add `tests/e2e/suites/workspace_owner/` to UPD-040's existing matrix-CI test path (3 modes: `mock`, `kubernetes`, `vault`). Verify all 7 test files pass in all 3 modes.
- [ ] T090 [W18C] Verify SC-018: J20 + J01 extension pass on the matrix CI for all 3 modes. If any mode fails, debug + fix.
- [ ] T091 [W18C] Run `pytest tests/e2e/suites/workspace_owner/ -v` against a kind cluster with the platform running → 7 test files pass.

**Checkpoint (end of Phase 4)**: 7 E2E test files + J20 + J01 extension all pass; matrix CI green for all 3 secret modes.

---

## Phase 5: Cross-Cutting Verification (Rule 31 + Rule 33 + Audit Emission)

**Story goal**: Verify Rule 31 (no plaintext secrets in logs) + Rule 33 (2PA invariants) + Rule 9 (every PII operation emits audit chain entry) + Rule 45 (every backend capability has UI).

- [ ] T092 [W18D] Run the canonical secret-leak regex set against `kubectl logs platform-control-plane-...` for 24 hours of synthetic load (connector test-connectivity + IBOR test-connection + transfer-ownership 2PA + connector secret rotation flows) per Rule 31; verify zero matches. Document in `specs/093-workspace-owner-workbench/contracts/secret-leak-verification.md` (NEW file).
- [X] T093 [W18D] Run UPD-040's `scripts/check-secret-access.py` (extended for any new code paths in this feature); verify zero direct `os.getenv("*_SECRET")` calls outside the `SecretProvider` implementation files.
- [ ] T094 [W18D] Verify all 8 new endpoints + 3 2PA endpoints emit audit-chain entries per Rule 9: synthetic test hits each state-changing endpoint; asserts `audit_chain_entries` row count grows by exactly 1 per call (or 2 for double-audit per Rule 34 — admin-on-behalf-of-user paths). Document in `specs/093-workspace-owner-workbench/contracts/audit-emission-verification.md` (NEW file).
- [ ] T095 [W18D] Verify Rule 33's 2PA invariants (foundational primitive verification): test-1 — same-actor approval rejected (design D4); test-2 — challenge expires after 5 minutes (Redis mirror + DB cleanup); test-3 — `consume` endpoint executes the FROZEN action_payload, NOT a client-resubmitted one (TOCTOU prevention per design D2); test-4 — atomic state transitions enforced via `SELECT FOR UPDATE` (concurrent approve calls — only first succeeds). Document in `specs/093-workspace-owner-workbench/contracts/2pa-rule33-verification.md` (NEW file).
- [X] T096 [W18D] Verify Rule 45 mapping: every Track A endpoint maps to a Track B page per spec.md Key Entities section. Synthetic test enumerates Track A endpoints + asserts a corresponding page exists at the documented URL. Failure means a backend capability has no UI surface — escalate.

---

## Phase 6: SC Verification + Documentation Polish

**Story goal**: All 20 spec SCs pass; UPD-039 docs integration; release notes; final review.

- [ ] T097 [W18E] Run the full SC verification sweep per the spec's 20 SCs. For each SC, document the actual measurement (e.g., SC-001's "3s dashboard load" — measured wall-clock with seeded data). Capture verification record at `specs/093-workspace-owner-workbench/contracts/sc-verification.md` (NEW file).
- [X] T098 [W18E] [US2] Create `docs/operator-guide/runbooks/workspace-owner-2pa.md` (NEW per plan.md design D14; deliverable here if UPD-039 has landed; otherwise UPD-039 owns and merges later). Sections: Symptom (operator wants to perform 2PA-gated action), Diagnosis (verify role + co-signer availability), Remediation (initiate → wait for approval → consume), Verification (audit chain shows double-audit), Rollback (challenge expires automatically; consumer can retry).
- [X] T099 [P] [W18E] [US3] Create `docs/operator-guide/runbooks/connector-self-service-troubleshooting.md`: workspace-owner connector setup issues — invalid credentials, rate-limit, third-party 429 handling.
- [X] T100 [P] [W18E] [US5] Create `docs/operator-guide/runbooks/ibor-connector-test-connection.md`: stepped diagnostic interpretation; common LDAP failures (DNS, TLS cert, bind credentials, BaseDN); links to Loki logs.
- [X] T101 [P] [W18E] Modify admin guide: add a "Workspace Owner Surfaces" section explaining the workspace-owner role + admin equivalents at `/admin/settings?tab=workspaces`. Document Rule 47 workspace vs platform scope distinction.
- [X] T102 [P] [W18E] Create `docs/developer-guide/2pa-primitive.md`: foundational 2PA primitive design + extensible `action_type` enum + how future destructive ops register handlers + Rule 33 invariants (TOCTOU prevention, same-actor refusal, atomic state transitions).
- [X] T103 [P] [W18E] [US3] Create `docs/developer-guide/connector-test-connectivity.md`: how to add a new connector type's `test_connectivity()` dry-run method + uniform `TestResult` shape per design D5 + Rule 31 no-plaintext-in-logs.
- [X] T104 [W18E] Modify `docs/release-notes/v1.3.0/workspace-owner-workbench.md` (NEW file or extend): document 8 new pages, 8 new endpoints, foundational 2PA primitive (reusable by future destructive ops), 9 new audit-event types, 4 connector dry-run methods. NO breaking changes (purely additive).
- [ ] T105 [W18E] Verify all 20 spec SCs pass (re-run T097); verify J20 + J01 extension + 7 E2E suites + 25 Playwright scenarios all pass on the matrix CI; verify zero secret-leak hits in 24-hour log capture per T092; verify Rule 33's 2PA invariants per T095; verify UPD-036's existing test suite passes unchanged (SC-020 — UPD-043 extends the admin tab pattern without breaking).
- [ ] T106 [W18E] Run `pytest apps/control-plane/tests/{two_person_approval,workspaces,connectors,auth}/`, `pytest tests/e2e/suites/workspace_owner/`, `pytest tests/e2e/journeys/test_j20_workspace_owner.py`, `pytest tests/e2e/journeys/test_j01_admin_bootstrap.py`, `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm test:i18n-parity` one final time → all pass.
- [X] T107 [W18E] Run `python scripts/check-secret-access.py` (UPD-040), `python scripts/check-admin-role-gates.py` (UPD-040), `python scripts/check-me-endpoint-scope.py` (UPD-042 — verifies `/me/*` endpoints don't accept `user_id`; UPD-043 endpoints are `/workspaces/{id}/*` so this check is informational) → all pass with zero violations.
- [X] T108 [W18E] If UPD-039 has landed, run `python scripts/check-doc-references.py` against new docs — verify FR-658 through FR-666 references in this feature's docs are valid + linked to section 116. CI fails any drift.
- [X] T109 [W18E] If UPD-039 has landed, run `python scripts/generate-env-docs.py` to verify no new env vars introduced by UPD-043 (this feature has no new env vars; confirm nothing leaked into `PlatformSettings`).
- [ ] T110 [W18E] Address PR review feedback; merge. Verify the `093-workspace-owner-workbench` branch passes all required CI gates (matrix-CI for 3 secret modes, secret-access check, role-gates check, axe-core AA scan, i18n parity); merge to `main`. **This is the FINAL feature in the v1.3.0 audit-pass cohort.**

---

## Dependencies & Execution Order

### Phase Dependencies

- **W18.0 Setup (T001-T004)**: No blockers; T001 verifies UPD-040 + UPD-041 + UPD-042 are on `main` (HARD DEPENDENCY).
- **W18A Track A Backend (T005-T035)**: Depends on W18.0 + UPD-040/041/042 shipped.
- **W18B Track B UI (T036-T078)**: Depends on Track A T021 + T032 (Pydantic schemas) — frontend Zod schemas mirror backend; T036-T043 can begin once schemas land; T044-T078 depend on full Track A endpoints functional.
- **W18C Track C E2E + journeys (T079-T091)**: Depends on Track A (endpoints functional) + Track B (UI for Playwright + journey-step page navigation).
- **W18D Cross-cutting verification (T092-T096)**: Depends on Track A + Track B (full flows must be runnable for log capture + audit emission verification).
- **W18E SC verification + docs (T097-T110)**: Depends on ALL OTHER PHASES — convergent.

### User Story Dependencies

- **US1 (P1 — workspace dashboard)**: T016-T017 (summary endpoint + service) + T044-T047 (dashboard pages) + T080 (E2E) + T087 (J20).
- **US2 (P1 — members + ownership transfer 2PA)**: T008-T015 (2PA primitive) + T018-T020 (transfer endpoints) + T048-T050 (members UI) + T081-T082 (E2E) + T087 (J20).
- **US3 (P1 — workspace connectors)**: T022-T028 (test-connectivity + 4 dry-run methods) + T056-T061 (connectors UI + 5-step wizard) + T083-T084 (E2E) + T087 (J20).
- **US4 (P2 — budget + hard cap)**: T051-T052 (settings page + budget form) + T085 (E2E) + T087 (J20).
- **US5 (P2 — IBOR admin wizard)**: T029-T031 (IBOR endpoints + service) + T067-T072 (admin tab + IBOR wizard) + T088 (J01 extension).
- **US6 (P3 — visibility explorer)**: T064-T066 (visibility page + XYFlow graph) + T086 (E2E) + T087 (J20).

### Within Each Track

- Track A: T005-T007 (migration + model) → T008-T015 (2PA BC) → T016-T021 (workspace endpoints) → T022-T028 (connector test-connectivity + dry-runs) → T029-T031 (IBOR endpoints) → T032-T035 (schemas + audit + tests).
- Track B: T036-T043 (scaffolding + hooks) → T044-T047 (dashboard) → T048-T055 (members + settings) → T056-T061 (connectors) → T062-T066 (quotas/tags/visibility) → T067-T072 (admin tabs) → T073-T078 (i18n + axe + Playwright).
- Track C: T079 (conftest) → T080-T086 (7 E2E files, parallel) → T087 (J20) → T088 (J01 ext) → T089-T091 (matrix CI).

### Parallel Opportunities

- **Day 1**: T001-T004 (Setup, all parallel) + T005-T007 (Track A migration + model) + T036 (Track B layout — independent) + T079 (Track C conftest scaffolding).
- **Day 2-3**: Track A T008-T028 sequential within sub-clusters; Track B T036-T055 (hooks + dashboard + members + settings) parallel by feature; Track C T080-T086 (7 E2E files) parallel.
- **Day 4-5**: Track A T029-T035 (IBOR + audit + tests); Track B T056-T072 (connectors + visibility + admin tabs) — highly parallel across 2 devs; Track C T087-T088 (journey tests).
- **Day 6**: Track B T073-T078 (i18n + axe + Playwright); Track C T089-T091 (matrix CI).
- **Day 7-9**: Phase 5 verification + Phase 6 polish (mostly parallel — runbooks + admin/dev guides parallel).

---

## Implementation Strategy

### MVP First (User Story 1 + 2 — Dashboard + Members)

1. Complete Phase 1 (W18.0) Setup.
2. Complete Phase 2 partial (W18A) Track A — migration + model + 2PA primitive (T005-T015) + workspace summary endpoint (T016-T017) + transfer-ownership (T018-T020).
3. Complete Phase 3 partial (W18B) Track B — layout + hooks + dashboard + members pages (T036-T050).
4. Run T080-T082 (E2E for US1 + US2).
5. **STOP and VALIDATE**: a workspace owner sees the dashboard with seeded data + can invite a member + can complete a 2PA-gated ownership transfer per SC-001 + SC-003 + SC-004.

### Incremental Delivery

1. MVP (US1 + US2) → demo workspace dashboard + 2PA ownership transfer.
2. + US3 (T022-T028, T056-T061, T083-T084) → demo workspace connector setup with test-connectivity.
3. + US4 (T051-T052, T085) → demo budget + hard cap.
4. + US5 (T029-T031, T067-T072, T088) → demo IBOR admin wizard.
5. + US6 (T064-T066, T086) → demo visibility explorer.
6. Full feature complete after Phase 5 + Phase 6 polish.

### Parallel Team Strategy

With 3 devs:

- **Dev A (Track A backend keystone)**: Days 1-4 Track A entire scope (migration + 2PA primitive + endpoints + service extensions + tests); Days 5-6 cross-cutting verification (Phase 5); Days 7-9 Phase 6 SC verification + 2PA runbook.
- **Dev B (Track B UI — pages 1-5 + admin tabs)**: Day 1 Track B layout + hooks; Days 2-4 dashboard + members + settings + connectors (T044-T061); Days 5-6 admin tab extensions + IBOR wizard (T067-T072); Days 7-9 connector + IBOR runbooks.
- **Dev C (Track B UI — pages 6-8 + Track C)**: Days 2-4 quotas + tags + visibility + visualization (T062-T066); Days 5-6 Track C E2E suite + journey tests + matrix CI (T079-T091); Days 7-9 admin/dev-guide pages.

Wall-clock: **5-6 days for MVP** (US1 + US2); **8-10 days for full feature** with 3 devs in parallel.

---

## Notes

- [P] tasks = different files, no dependencies; safe to parallelize across devs.
- [Story] label maps task to specific user story for traceability (US1-US6).
- [W18X] label maps task to wave-18 sub-track (W18.0 / W18A-E).
- The plan's effort estimate (11-13 dev-days) supersedes the brownfield's 6-day understatement; tasks below total ~110 entries, consistent with that estimate.
- **Track A's foundational 2PA primitive is the highest-risk piece**; rushing it risks rework + security holes in future destructive ops. Plan ≥ 2 dev-days. T011-T015 + T095 verification are mandatory.
- Rule 31 (never log secrets) is enforced at THREE layers: Track A (no plaintext in audit metadata), UPD-040 deny-list (T093), 24-hour log capture verification (T092).
- Rule 33 (2PA enforced server-side) is verified by T095's 4 invariant tests (same-actor refusal, TTL expiry, TOCTOU prevention, atomic transitions).
- Rule 9 (PII operations emit audit) is enforced by T033 wiring 9 new event types + T094 verification.
- Rule 45 (every backend capability has UI) is the canonical anchor — T096 verifies the mapping holistically.
- Rule 47 (workspace vs platform scope distinction) is verified by T067's admin tab extensions distinguishing admin-global views from workspace-owner views.
- The 8 new endpoints + 3 2PA endpoints = 11 net-new endpoints; the existing 18 workspace + 14 connector + 5 IBOR endpoints (37 total) are PRESERVED unchanged.
- The 2PA primitive's `action_type` enum is extensible per design D3; future destructive ops (e.g., `super_admin_password_reset`, `vault_unseal_quorum_share`, `workspace_archive`) can register handlers without modifying the primitive.
- **UPD-043 is the FINAL feature in the v1.3.0 audit-pass cohort.** Per spec User Story 5 + plan.md "Wave Placement", merging UPD-043 closes the cohort.
