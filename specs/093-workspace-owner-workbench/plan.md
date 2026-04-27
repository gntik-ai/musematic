# Implementation Plan: UPD-043 — Workspace Owner Workbench and Connector Self-Service

**Branch**: `093-workspace-owner-workbench` | **Date**: 2026-04-27 | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

## Summary

UPD-043 is the v1.3.0 audit-pass cohort's penultimate feature and a **mostly-UI gap-fill** delivering 8 NEW Next.js workspace-scoped pages + 3 admin tab extensions on top of an extensive but invisible workspace + connector + IBOR backend. The brownfield's premise that "today connectors are platform-owned only" is INCORRECT per spec correction §3 + research R10 — connectors are ALREADY workspace-scoped (`ConnectorInstance.workspace_id` NOT NULL at `connectors/models.py:89-92`) and 14 workspace-scoped endpoints exist at `connectors/router.py:82-237`. The actual contribution is the workspace-owner UI surface + 5 net-new backend endpoints + 1 NEW 2PA infrastructure primitive (greenfield per Constitution Rule 33). Three parallelizable tracks converge for journey-test verification:

- **Track A — Backend additions** (~3.5 dev-days): NEW `workspaces/router.py` extension with 2 endpoints (`GET /workspaces/{id}/summary` aggregator, `POST /workspaces/{id}/transfer-ownership`); NEW `connectors/router.py` extension with 1 endpoint (`POST /workspaces/{wid}/connectors/{cid}/test-connectivity` per FR-662 — distinct from the existing `health-check` per spec correction §6); NEW `auth/router.py` extension with 3 IBOR endpoints (`POST /admin/ibor/{id}/test-connection`, `POST /admin/ibor/{id}/sync-now`, `GET /admin/ibor/{id}/sync-history` exposing the existing `IBORConnectorService.list_sync_runs` per research R3); NEW foundational 2PA primitive — `TwoPersonApprovalChallenge` model (NEW table) + 3 endpoints (request / approve / consume) per spec correction §12 + Rule 33; per-connector dry-run `test_connectivity()` methods on the 4 existing connector implementations (Slack `auth.test`-equivalent per research R10 — does NOT exist today, this feature adds it); 9 new audit-event types; Alembic migration `071_workspace_owner_workbench.py` (next slot per research R11 — verified — UPD-040/041/042 own 069-070); 3 NEW JSONB columns on `WorkspaceSettings` (`quota_config`, `dlp_rules`, `residency_config`) extending the existing 5 ARRAY + 1 JSONB surface verified at `workspaces/models.py:208-248`.

- **Track B — Frontend pages** (~5.5 dev-days): 8 NEW Next.js pages under `/workspaces/[id]/*` (entire route tree is new per spec correction §9 — no existing `/workspaces/[id]/*` UI); 3 admin tab extensions to the existing `AdminSettingsPanel.tsx` (verified per research R2 — tabs auto-register via array at lines 16-39): 2 already-existing tabs are extended (`?tab=connectors` for the global connector view, `?tab=quotas` for global quotas) + 1 NEW tab (`?tab=workspaces` for admin global workspace view) + 1 EXTENDED tab (`?tab=ibor` — currently in the existing array; this feature ADDS the wizard sub-features per FR-664). Visibility explorer uses XYFlow + Dagre per spec correction §5 + research R9 — modeled on the existing `HypothesisNetworkGraph.tsx` (discovery workbench) + `FleetTopologyGraph.tsx` (fleet dashboard) precedents. ~30 sub-components; ~80 i18n keys × 6 locales = 480 entries; axe-core AA per Rule 41.

- **Track C — E2E + journey** (~2.5 dev-days): NEW `tests/e2e/journeys/test_j20_workspace_owner.py` per FR-666 + spec correction §11 (J20 does NOT exist on disk — only J01-J04 + J10 exist; J19 is created in UPD-042). NEW `tests/e2e/suites/workspace_owner/` with 7 test files. EXTENDS J01 with the IBOR admin wizard. Matrix-CI inheritance from UPD-040 for 3 secret modes.

The three tracks converge at Phase 7 for SC verification + auto-doc verification. **Effort estimate: 11-13 dev-days** (the brownfield's "6 days (6 points)" understates by ~50% — consistent with v1.3.0 cohort pattern. Brownfield understates because: (a) does not account for the foundational 2PA primitive — greenfield per Rule 33 + research §15; (b) misses the 4 connector implementations needing new `test_connectivity()` methods per research R10 — does NOT exist today; (c) misses the 3 NEW JSONB columns on `WorkspaceSettings` + Alembic migration; (d) misses the 9 new audit-event types; (e) the i18n catalogs across 6 locales × 80 entries; (f) misses J20 creation as a fresh ~250-line test file modeled on J04. Wall-clock with 3 devs in parallel: **~5-6 days**.

## Constitutional Anchors

This plan is bounded by the following Constitution articles + FRs. Each implementation step below cites the article it serves.

| Anchor | Citation | Implementation tie |
|---|---|---|
| **UPD-043 declared** | Constitution audit-pass roster (Wave 18) | The whole feature |
| **Rule 9 — Every PII operation emits an audit chain entry** | `.specify/memory/constitution.md` (verified existing) | Track A's 9 new audit-event types (`auth.workspace.member_added`, `auth.workspace.transfer_initiated`, `auth.workspace.transfer_committed`, `auth.workspace.budget_updated`, etc.) |
| **Rule 10 — Every credential goes through vault** | `.specify/memory/constitution.md:123-126` | Track A's connector secrets path per spec correction §10 — `secret/data/musematic/{env}/connectors/workspace-{wid}/{cid}` (canonical UPD-040 scheme); Track A's IBOR credential storage |
| **Rule 30 — Every admin endpoint declares a role gate** | `.specify/memory/constitution.md:198-202` | Track A's 3 new IBOR admin endpoints depend on `_require_platform_admin`; Track A's 2PA admin-co-signer endpoint depends on platform-admin role |
| **Rule 33 — 2PA enforced server-side** | `.specify/memory/constitution.md:213-216` (verified per spec correction §15) | Track A's foundational 2PA primitive — `TwoPersonApprovalChallenge` model + 3 endpoints; Track A's `POST /workspaces/{id}/transfer-ownership` requires a 2PA-consumed token. The brownfield's "FR-561 + FR-559" map to Rule 33's enforcement contract. |
| **Rule 41 — Accessibility AA** | `.specify/memory/constitution.md` | Track B's axe-core CI gate — all 8 new pages + 3 tab extensions MUST pass AA per UPD-083 inheritance |
| **Rule 45 — Every user-facing backend capability has UI** | `.specify/memory/constitution.md:258-262` | THE canonical anchor — UPD-043 IS the Rule 45 gap-fill for the workspace + connector + IBOR backends |
| **Rule 46 — Self-service `/me/*` endpoints scoped to `current_user`** | `.specify/memory/constitution.md:263-267` | N/A for `/workspaces/{id}/*` per spec correction (these are workspace-scoped, NOT user-self-scoped) |
| **Rule 47 — Workspace vs platform scope distinction** | `.specify/memory/constitution.md` (verified existing) | Track A + Track B's connector "workspace-owned" badge per spec correction §3 + §4 |
| **FR-658 — Workspace Owner Dashboard** | FR doc lines 3540+ (verified per spec correction §14) | Track A `GET /summary` + Track B dashboard page |
| **FR-659 — Workspace Members Management** | FR doc | Track B `/members` page; Track A `POST /transfer-ownership` (2PA) |
| **FR-660 — Workspace Settings Page** | FR doc | Track B `/settings` page reading 4 JSONB columns (1 existing + 3 NEW) |
| **FR-661 — Workspace-Owned Connectors** | FR doc | Track B `/connectors` page consuming existing 14 endpoints + new `test-connectivity` per spec correction §3 + §6 |
| **FR-662 — Connector Setup Wizards** | FR doc | Track A's connector dry-run methods + Track B's 4 wizard variants (Slack/Telegram/Email/Webhook) |
| **FR-663 — Connector Activity and Diagnostics** | FR doc | Track B's activity panel reading from existing `outbound_deliveries` table per research R5 |
| **FR-664 — IBOR Connector Management for Admins** | FR doc | Track A's 3 IBOR endpoints + Track B's IBOR tab extensions (test-connection / mapping / sync-history) |
| **FR-665 — Workspace Visibility Explorer** | FR doc | Track B's XYFlow + Dagre graph per research R9 (NOT Cytoscape) |
| **FR-666 — Workspace Owner Workbench E2E Coverage** | FR doc | Track C's J20 + 7 suite tests + J01 extension |

**Verdict: gate passes. No declared variances.** UPD-043 satisfies all eight constitutional rules governing workspace + connector + IBOR + 2PA.

## Technical Context

| Item | Value |
|---|---|
| **Languages** | Python 3.12 (control plane — extension of `workspaces/router.py` + `connectors/router.py` + `auth/router.py` + new `two_person_approval/` BC + 4 connector dry-run methods + Alembic migration); TypeScript 5.x (Next.js 14 — 8 new pages + 3 admin tab extensions); YAML (no Helm changes — backend reuses existing infrastructure). NO Go changes. |
| **Primary Dependencies (existing — reused)** | `FastAPI 0.115+`, `pydantic-settings 2.x`, `SQLAlchemy 2.x async`, `aiokafka 0.11+` (audit-event emission), `redis-py 5.x async` (2PA challenge TTL via Redis hash), `react 18+`, `next 14`, `shadcn/ui` (existing primitives — `Tabs`, `Dialog`, `Stepper`, `Table`, `Badge`), `Zustand 5.x` (existing `useAuthStore`), `TanStack Query v5`, `next-intl` (i18n), `@xyflow/react ^12.10.2` + `@dagrejs/dagre ^3.0.0` (existing graph stack per research R9). |
| **Primary Dependencies (NEW in 093)** | NO new runtime dependencies. The 2PA primitive uses existing PostgreSQL + Redis. Visibility graph reuses existing XYFlow + Dagre per spec correction §5 + research R9 (Cytoscape NOT introduced). |
| **Storage** | PostgreSQL — Alembic migration `071_workspace_owner_workbench.py` (next slot per research R11 — UPD-040/041/042 own 069-070): (a) extends `WorkspaceSettings` (lines 208-248 per research R1) with 3 NEW JSONB columns — `quota_config`, `dlp_rules`, `residency_config` (preserves the existing 5 ARRAY + 1 `cost_budget` JSONB); (b) NEW table `two_person_approval_challenges` per spec correction §12 + Rule 33 — columns: `id`, `action_type` (enum: `workspace_transfer_ownership` initially; extensible by future destructive ops), `action_payload` (JSONB — frozen action spec), `initiator_id` (UUID FK users), `co_signer_id` (UUID FK users — nullable until approved), `status` (enum: `pending` / `approved` / `consumed` / `expired`), `created_at`, `expires_at` (default `created_at + 5min`), `approved_at`, `consumed_at`. Redis — 1 NEW key namespace `2pa:challenge:{id}` (TTL = 5 minutes; mirror of the table for fast lookup). NO MinIO / Qdrant changes. NO Vault new paths owned by this feature (connector secrets reuse the existing UPD-040 canonical scheme per spec correction §10). |
| **Testing** | `pytest 8.x` + `pytest-asyncio` (control plane unit tests for 8 new endpoints + 9 audit-event types + 4 connector dry-run methods + 2PA primitive — ~60+ test cases); Playwright (Next.js page E2E for 8 pages + 3 admin tab extensions — ~25+ scenarios); axe-core CI gate per Rule 41; pytest E2E suite at `tests/e2e/suites/workspace_owner/` — 7 test files. J20 creation (~250 lines modeled on J04 verified at 31,924 bytes per research §17 of spec phase). J01 extension (~30 lines for IBOR wizard). Matrix-CI inheritance from UPD-040: `secret_mode: [mock, kubernetes, vault]` × `workspace_owner` suite. |
| **Target Platform** | Linux x86_64 Kubernetes 1.28+ (control plane); Next.js 14 server + browser (web app). |
| **Project Type** | Cross-stack feature: (a) Python control plane (`apps/control-plane/` — extensions to `workspaces/`, `connectors/`, `auth/` BCs + new `two_person_approval/` BC + 4 connector implementations); (b) Next.js frontend (`apps/web/` — 8 new pages + 3 admin tab extensions); (c) E2E test scaffolding. NO Helm/Go changes. |
| **Performance Goals** | Workspace dashboard summary endpoint ≤ 800ms p95 (aggregator query against multiple BCs — needs Redis-backed cache for hot path); workspace dashboard first-paint ≤ 3 seconds per SC-001; connector test-connectivity ≤ 10 seconds per SC-006 (network round-trip dominant); IBOR test-connection ≤ 10 seconds per SC-012 (DNS+TLS+bind+sample-query stepped); visibility explorer renders ≤ 500 nodes in ≤ 1 second per SC-014 (XYFlow + Dagre); 2PA challenge TTL = 5 minutes (Redis-backed). |
| **Constraints** | Rule 33 — 2PA challenge MUST be validated server-side on apply (NEVER client-only); Rule 10 — connector + IBOR credentials MUST flow through Vault (Rule 39 from UPD-040 — SecretProvider; CI deny-list catches violations); Rule 45 — every backend `/workspaces/{id}/*` AND `/admin/ibor/*` capability MUST have a UI page (verified by mapping each Track A endpoint to a Track B page); FR-662 — test-connectivity MUST NOT send user-visible messages (verified by SC-006 + dedicated E2E test per User Story 3 acceptance scenario 3). |
| **Scale / Scope** | Track A: ~5 NEW Python endpoints (`/summary`, `/transfer-ownership`, `/test-connectivity`, IBOR `/test-connection` + `/sync-now` + `/sync-history`) + ~3 NEW 2PA endpoints + 4 connector dry-run methods (~40 lines each) + 1 Alembic migration (~80 lines) + 1 NEW 2PA BC (`apps/control-plane/src/platform/two_person_approval/` ~400 lines) + ~150 lines of Pydantic schemas + 9 NEW audit-event payload classes + ~60 unit tests. Track B: 8 NEW pages (~250 lines × 8 = ~2000 lines) + ~30 NEW shared sub-components (~80 lines × 30 = ~2400 lines) + 3 admin tab extensions (~150 lines each = ~450 lines) + 6 i18n catalogs × ~80 strings each = ~480 i18n entries + ~25 Playwright scenarios. Track C: 7 NEW E2E test files (~80 lines each = ~560 lines) + J20 creation (~250 lines) + J01 extension (~30 lines). **Total: ~6500 lines of new Python + TypeScript + ~480 i18n entries; ~50 NEW files + ~10 MODIFIED files.** |

## Constitution Check

> **GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.**

| Check | Verdict | Rationale |
|---|---|---|
| Brownfield rule — modifications respect existing repo discipline | ✅ Pass | UPD-043 (a) EXTENDS the existing 18-endpoint workspaces router (verified per spec phase research §1) with 2 new endpoints; (b) EXTENDS the existing 14-endpoint connectors router with 1 new endpoint per spec correction §3 + §6; (c) EXTENDS the existing 5-endpoint IBOR admin router with 3 new endpoints per spec correction §13; (d) ADDS the foundational 2PA primitive as a NEW `two_person_approval/` BC (greenfield — no existing 2PA implementation per Rule 33); (e) PRESERVES the existing `cost_budget` JSONB unchanged + adds 3 new JSONB columns; (f) PRESERVES the existing 4 connector implementations + adds dry-run methods. |
| Rule 9 — every PII operation emits audit chain entry | ✅ Pass | All 9 new audit-event types follow the existing dual-emission pattern (`repository.create_audit_entry` + `publish_auth_event` per UPD-040 / UPD-042 research R6). |
| Rule 10 — every credential goes through vault | ✅ Pass | Connector secrets stored at `secret/data/musematic/{env}/connectors/workspace-{wid}/{cid}` per spec correction §10 (canonical UPD-040 scheme); IBOR credentials at `secret/data/musematic/{env}/ibor/{connector_id}/credentials` per spec FR-664. UPD-040's `scripts/check-secret-access.py` deny-list catches any new code paths logging secrets. |
| Rule 30 — every admin endpoint role-gated | ✅ Pass | Track A's 3 new IBOR endpoints depend on `_require_platform_admin` per the existing pattern at `auth/router.py:176-229`; the 2PA approve endpoint depends on platform-admin role per Rule 33. |
| Rule 33 — 2PA enforced server-side | ✅ Pass (NEW INFRASTRUCTURE) | Track A's foundational 2PA primitive enforces server-side: the `TwoPersonApprovalChallenge.status` transitions are validated atomically on every endpoint hit; the consumed-once invariant is enforced by `consumed_at IS NOT NULL` check; the action-payload is FROZEN at challenge creation (the `consume` endpoint executes exactly that payload, NOT a client-resubmitted one — preventing TOCTOU per Rule 33's "Servers validate the 2PA token freshly on apply"). |
| Rule 41 — Accessibility AA | ✅ Pass | Track B's 8 new pages + 3 admin tab extensions pass axe-core AA scan (CI gate inherited from UPD-083); verified by SC-016. |
| Rule 45 — every user-facing backend capability has UI | ✅ Pass | THE canonical anchor — UPD-043 IS the Rule 45 gap-fill for the workspaces + connectors + IBOR backends. Every Track A endpoint maps to a Track B page (verified by spec Key Entities section). |
| Rule 47 — workspace vs platform scope distinction | ✅ Pass | Track B's connector page renders a "workspace-owned" badge on each connector card per spec correction §3; admin tab extensions cover platform-global views. |

**Verdict: gate passes. No declared variances. UPD-043 satisfies all eight constitutional rules.**

## Project Structure

### Documentation (this feature)

```text
specs/093-workspace-owner-workbench/
├── plan.md                # this file
├── spec.md
├── planning-input.md
└── tasks.md               # produced by /speckit.tasks (next phase)
```

### Source Code (repository root) — files this feature creates or modifies

```text
# === Track A — Backend additions ===
apps/control-plane/migrations/versions/071_workspace_owner_workbench.py  # NEW — Alembic migration adding 3 JSONB columns to WorkspaceSettings + 1 NEW table two_person_approval_challenges
apps/control-plane/src/platform/workspaces/models.py                     # MODIFY — extends WorkspaceSettings (lines 208-248 verified per research R1) with 3 NEW JSONB columns: quota_config, dlp_rules, residency_config
apps/control-plane/src/platform/workspaces/router.py                     # MODIFY — adds 2 NEW endpoints per spec scope discipline: GET /workspaces/{id}/summary (aggregator), POST /workspaces/{id}/transfer-ownership (2PA-gated). The existing 18 endpoints (lines 50-346 verified per spec phase research §1) are preserved unchanged.
apps/control-plane/src/platform/workspaces/service.py                    # MODIFY — adds get_summary(workspace_id, requester_id) -> WorkspaceSummaryResponse method aggregating goals + executions + agents + budget gauge + quota usage + tag summary + DLP violations + recent activity per FR-658; adds initiate_ownership_transfer(workspace_id, new_owner_id, requester_id) -> TwoPersonApprovalChallenge per FR-659 + Rule 33; adds commit_ownership_transfer(challenge_id, requester_id) -> WorkspaceResponse
apps/control-plane/src/platform/workspaces/schemas.py                    # MODIFY — adds WorkspaceSummaryResponse + TransferOwnershipRequest + WorkspaceQuotaConfig + WorkspaceDLPRules + WorkspaceResidencyConfig (~6 new schemas)
apps/control-plane/src/platform/connectors/router.py                     # MODIFY — adds 1 NEW endpoint POST /workspaces/{wid}/connectors/{cid}/test-connectivity per FR-662 + spec correction §6 (distinct from existing /health-check at line 158 per research R4). The existing 14 endpoints (lines 82-237 verified per spec phase research §5) are preserved unchanged.
apps/control-plane/src/platform/connectors/service.py                    # MODIFY — adds test_connectivity(workspace_id, connector_instance_id, candidate_config) -> TestConnectivityResponse method that invokes the connector implementation's NEW test_connectivity() dry-run method
apps/control-plane/src/platform/connectors/implementations/slack.py      # MODIFY — adds async def test_connectivity(self, config, credential_refs) -> TestResult method per research R10 (does NOT exist today). Uses Slack auth.test API for dry-run validation without sending user-visible messages.
apps/control-plane/src/platform/connectors/implementations/telegram.py   # MODIFY — adds test_connectivity using getMe API (validates bot token without sending messages)
apps/control-plane/src/platform/connectors/implementations/email.py      # MODIFY — adds test_connectivity using SMTP/IMAP NOOP commands (validates auth without sending email)
apps/control-plane/src/platform/connectors/implementations/webhook.py    # MODIFY — adds test_connectivity using HEAD request to webhook URL (validates URL reachable + HMAC config without POST)
apps/control-plane/src/platform/auth/router.py                           # MODIFY — adds 3 NEW IBOR admin endpoints per FR-664 + spec correction §13: POST /api/v1/auth/ibor/connectors/{id}/test-connection, POST /api/v1/auth/ibor/connectors/{id}/sync-now, GET /api/v1/auth/ibor/connectors/{id}/sync-history. Each calls _require_platform_admin per Rule 30.
apps/control-plane/src/platform/auth/ibor_service.py                     # MODIFY — adds test_connection(connector_id) -> TestConnectionResponse method (DNS + TLS + bind + sample-query diagnostic flow per FR-664) + sync_now(connector_id) -> SyncRunResponse method invoking existing IBORSyncService.trigger_sync per research R3 + get_sync_history(connector_id, limit, cursor) -> list[IBORSyncRunResponse] (exposes existing list_sync_runs as a new endpoint)
apps/control-plane/src/platform/two_person_approval/__init__.py          # NEW — module marker
apps/control-plane/src/platform/two_person_approval/models.py            # NEW (~80 lines) — TwoPersonApprovalChallenge model per spec correction §12: action_type enum, action_payload JSONB, initiator_id, co_signer_id, status enum (pending/approved/consumed/expired), created_at, expires_at, approved_at, consumed_at
apps/control-plane/src/platform/two_person_approval/router.py            # NEW (~150 lines) — 3 new endpoints: POST /api/v1/2pa/challenges, POST /api/v1/2pa/challenges/{id}/approve (admin co-signer), POST /api/v1/2pa/challenges/{id}/consume (action proceeds with consumed token)
apps/control-plane/src/platform/two_person_approval/service.py           # NEW (~200 lines) — TwoPersonApprovalService with create_challenge, approve_challenge, consume_challenge methods. Atomic state transitions via SELECT FOR UPDATE. 5-minute TTL via Redis hash mirror.
apps/control-plane/src/platform/two_person_approval/schemas.py           # NEW (~80 lines) — Pydantic schemas
apps/control-plane/src/platform/main.py                                  # MODIFY — registers new 2PA router via app.include_router(two_pa_router, prefix="/api/v1") AFTER the existing workspaces router registration
apps/control-plane/tests/two_person_approval/test_router.py              # NEW — pytest tests for 3 new 2PA endpoints (~12 cases)
apps/control-plane/tests/two_person_approval/test_service.py             # NEW — pytest tests for atomic state transitions + TTL expiry + same-actor refusal per spec edge case (~10 cases)
apps/control-plane/tests/workspaces/test_summary_endpoint.py             # NEW — pytest tests for /summary aggregator (~8 cases)
apps/control-plane/tests/workspaces/test_transfer_ownership.py           # NEW — pytest tests for 2PA-gated transfer (~10 cases)
apps/control-plane/tests/connectors/test_test_connectivity.py            # NEW — pytest tests for 4 connector dry-run methods (~16 cases)
apps/control-plane/tests/auth/test_ibor_admin_endpoints.py               # NEW — pytest tests for 3 new IBOR endpoints (~12 cases)

# === Track B — Frontend pages ===
apps/web/app/(main)/workspaces/page.tsx                                  # NEW — workspaces list (~200 lines)
apps/web/app/(main)/workspaces/[id]/page.tsx                             # NEW — dashboard (~250 lines)
apps/web/app/(main)/workspaces/[id]/_components/WorkspaceDashboardCard.tsx  # NEW (~80 lines × 7 cards = ~560 lines aggregated; one component per card type)
apps/web/app/(main)/workspaces/[id]/members/page.tsx                     # NEW — members management (~250 lines)
apps/web/app/(main)/workspaces/[id]/members/_components/InviteMemberDialog.tsx  # NEW (~150 lines)
apps/web/app/(main)/workspaces/[id]/members/_components/TransferOwnershipDialog.tsx  # NEW (~200 lines) — 2PA challenge initiation + status display
apps/web/app/(main)/workspaces/[id]/settings/page.tsx                    # NEW — settings with 4 sub-domains (~250 lines)
apps/web/app/(main)/workspaces/[id]/settings/_components/BudgetForm.tsx  # NEW (~150 lines) — reuses existing cost_budget JSONB
apps/web/app/(main)/workspaces/[id]/settings/_components/QuotaConfigForm.tsx  # NEW (~150 lines) — NEW quota_config JSONB
apps/web/app/(main)/workspaces/[id]/settings/_components/DLPRulesForm.tsx  # NEW (~150 lines) — NEW dlp_rules JSONB extending UPD-076/078 globals
apps/web/app/(main)/workspaces/[id]/settings/_components/ResidencyForm.tsx  # NEW (~120 lines) — NEW residency_config JSONB
apps/web/app/(main)/workspaces/[id]/connectors/page.tsx                  # NEW — connectors list with workspace-owned badge (~200 lines)
apps/web/app/(main)/workspaces/[id]/connectors/[connectorId]/page.tsx    # NEW — connector detail with activity panel (~250 lines)
apps/web/app/(main)/workspaces/[id]/connectors/_components/ConnectorSetupWizard.tsx  # NEW (~400 lines) — 5-step shared stepper
apps/web/app/(main)/workspaces/[id]/connectors/_components/SlackWizardSteps.tsx  # NEW (~150 lines)
apps/web/app/(main)/workspaces/[id]/connectors/_components/TelegramWizardSteps.tsx  # NEW (~120 lines)
apps/web/app/(main)/workspaces/[id]/connectors/_components/EmailWizardSteps.tsx  # NEW (~150 lines)
apps/web/app/(main)/workspaces/[id]/connectors/_components/WebhookWizardSteps.tsx  # NEW (~120 lines)
apps/web/app/(main)/workspaces/[id]/connectors/_components/ConnectorActivityPanel.tsx  # NEW (~200 lines) — reads from existing outbound_deliveries table per research R5
apps/web/app/(main)/workspaces/[id]/connectors/_components/RotateSecretDialog.tsx  # NEW (~150 lines) — UPD-040 KV v2 rotation
apps/web/app/(main)/workspaces/[id]/quotas/page.tsx                      # NEW — quota visualization + edit (~200 lines)
apps/web/app/(main)/workspaces/[id]/tags/page.tsx                        # NEW — workspace tags (~180 lines)
apps/web/app/(main)/workspaces/[id]/visibility/page.tsx                  # NEW — XYFlow + Dagre graph per spec correction §5 + research R9 (~250 lines)
apps/web/app/(main)/workspaces/[id]/visibility/_components/VisibilityGraph.tsx  # NEW (~300 lines) — modeled on `HypothesisNetworkGraph.tsx` + `FleetTopologyGraph.tsx` precedents per research R9
apps/web/app/(main)/workspaces/[id]/visibility/_components/GrantDetailPanel.tsx  # NEW (~150 lines)
apps/web/components/layout/WorkspaceOwnerLayout.tsx                      # NEW (~150 lines) — sidebar nav for /workspaces/[id]/* route group
apps/web/components/features/admin/AdminSettingsPanel.tsx                # MODIFY — adds 1 NEW tab `?tab=workspaces` to the existing tabs array (lines 16-39 per research R2); EXTENDS the existing `?tab=ibor` tab content with the new wizard sub-features (test-connection / mapping / sync-history). Existing 7 tabs preserved unchanged.
apps/web/components/features/admin/_tabs/WorkspacesTab.tsx               # NEW (~250 lines) — admin global view of all workspaces
apps/web/components/features/admin/_tabs/IBORTab.tsx                     # MODIFY (or CREATE if not present per research R2) — extends with NEW IBORConnectorWizard + AttributeMappingWizard + SyncHistoryDrillDown
apps/web/components/features/admin/_tabs/_components/IBORConnectorWizard.tsx  # NEW (~400 lines) — 7-step LDAP/OIDC/SCIM wizard
apps/web/components/features/admin/_tabs/_components/AttributeMappingWizard.tsx  # NEW (~250 lines) — schema-aware source → platform field mapper
apps/web/components/features/admin/_tabs/_components/SyncHistoryDrillDown.tsx  # NEW (~200 lines) — paginated sync history + Loki link
apps/web/lib/api/workspace-owner.ts                                      # NEW — fetch wrappers for new endpoints
apps/web/lib/schemas/workspace-owner.ts                                  # NEW — Zod schemas
apps/web/lib/hooks/use-workspace-summary.ts                              # NEW — TanStack Query hook
apps/web/lib/hooks/use-2pa-challenge.ts                                  # NEW — TanStack Query hook for the 3 2PA endpoints
apps/web/lib/hooks/use-connector-test-connectivity.ts                    # NEW
apps/web/lib/hooks/use-ibor-admin.ts                                     # NEW — hooks for test-connection / sync-now / sync-history
apps/web/messages/en.json                                                # MODIFY — adds ~80 new i18n keys under `workspaces.{dashboard,members,settings,connectors,quotas,tags,visibility}.*` + `admin.{ibor,workspaces}.*` namespaces
apps/web/messages/{de,es,fr,it,zh-CN,ja}.json                            # MODIFY — translated catalogs (vendor-handled per UPD-039)
apps/web/tests/e2e/workspace-owner-pages.spec.ts                         # NEW — Playwright tests for 8 new pages + 3 admin tab extensions (~25 scenarios)

# === Track C — E2E + journey ===
tests/e2e/suites/workspace_owner/__init__.py                             # NEW
tests/e2e/suites/workspace_owner/conftest.py                             # NEW — shared fixtures (workspace_with_seeded_data, workspace_with_connectors, multi-member workspace)
tests/e2e/suites/workspace_owner/test_dashboard_scoped.py                # NEW — User Story 1 (~5 cases)
tests/e2e/suites/workspace_owner/test_member_management.py               # NEW — User Story 2 (~5 cases)
tests/e2e/suites/workspace_owner/test_ownership_transfer_2pa.py          # NEW — User Story 2 + 2PA primitive (~6 cases)
tests/e2e/suites/workspace_owner/test_workspace_connector_slack.py       # NEW — User Story 3 (~5 cases)
tests/e2e/suites/workspace_owner/test_workspace_connector_webhook.py     # NEW — User Story 3 (~5 cases)
tests/e2e/suites/workspace_owner/test_workspace_budget_enforcement.py    # NEW — User Story 4 (~5 cases)
tests/e2e/suites/workspace_owner/test_visibility_explorer.py             # NEW — User Story 6 (~4 cases)
tests/e2e/journeys/test_j20_workspace_owner.py                           # NEW (~250 lines) — modeled on J04 verified at 31,924 bytes
tests/e2e/journeys/test_j01_admin_bootstrap.py                           # MODIFY — adds IBOR admin wizard steps (~30 lines)
.github/workflows/ci.yml                                                 # MODIFY — adds tests/e2e/suites/workspace_owner/ to UPD-040's matrix-CI test path
```

**Structure decision**: UPD-043 follows the brownfield repo discipline. The new `/workspaces/[id]/*` UI route tree is colocated with route-group `(main)` per the existing convention. The 8 NEW pages each have `_components/` subdirectories for page-scoped sub-components per the UPD-042 precedent. The new `two_person_approval/` BC at `apps/control-plane/src/platform/two_person_approval/` follows the existing BC pattern (models + router + service + schemas + tests). NO new BCs introduced beyond 2PA; existing BCs (workspaces, connectors, auth) are extended.

## Phase 0 — Research

> Research notes captured during plan authoring. Each item resolves a specific design question.

- **R1 — `WorkspaceSettings` schema extension [RESEARCH-COMPLETE]**: Verified at `workspaces/models.py:208-248`. Existing 5 ARRAY columns + 1 JSONB (`cost_budget`). **Resolution**: 3 NEW JSONB columns added via Alembic migration `071`: `quota_config: JSONB` (per-resource quotas), `dlp_rules: JSONB` (workspace-scoped DLP overrides extending UPD-076/078 globals), `residency_config: JSONB` (data-residency tier). Backward-compat: NOT NULL DEFAULT '{}'.

- **R2 — `AdminSettingsPanel.tsx` tab pattern [RESEARCH-COMPLETE]**: Verified at lines 16-39. Existing 7 tabs registered in array (`users`, `signup`, `quotas`, `connectors`, `email`, `oauth`, `security`). **Resolution**: UPD-043 ADDS 1 new tab `workspaces` to the array; EXTENDS the existing `connectors` and `quotas` tabs with admin-global views; EXTENDS the existing `oauth` tab is preserved (UPD-041 already shipped); INTRODUCES a NEW `ibor` tab (NOT in the existing array per research R2 — needs verification during T037; if the existing array already has `ibor`, this feature ONLY extends; if not, this feature adds the entry).

- **R3 — IBOR service method extensions [RESEARCH-COMPLETE]**: Verified at `auth/ibor_service.py:18-79` (existing methods: `create_connector`, `list_connectors`, `get_connector`, `update_connector`, `delete_connector`, `list_sync_runs`) + `auth/ibor_sync.py:39-80` (existing `trigger_sync`). **Resolution**: 3 NEW methods on `IBORConnectorService`: `test_connection(connector_id) -> TestConnectionResponse` (DNS + TLS + bind + sample-query stepped diagnostic), `sync_now(connector_id) -> SyncRunResponse` (delegates to existing `IBORSyncService.trigger_sync`), `get_sync_history(connector_id, limit, cursor)` (delegates to existing `list_sync_runs` with pagination).

- **R4 — `/health-check` vs `/test-connectivity` distinction [RESEARCH-COMPLETE]**: Verified at `connectors/router.py:158-169`. Existing `/health-check` validates EXISTING connector instance credentials (passive monitoring). **Resolution**: NEW `/test-connectivity` is a wizard-time endpoint validating a CANDIDATE config BEFORE saving (dry-run path per connector type per research R10). The two endpoints coexist — NO replacement.

- **R5 — `outbound_deliveries` activity panel data source [RESEARCH-COMPLETE]**: Verified at `connectors/models.py:216-267`. Schema: `workspace_id`, `connector_instance_id`, `destination`, `status` (pending/in_flight/delivered/failed/dead_lettered), `attempt_count`, `delivered_at`, `error_history`. Indexes on `(connector_instance_id, status)`. **Resolution**: The activity panel page (`ConnectorActivityPanel.tsx`) queries via the existing `GET /workspaces/{wid}/connectors/{cid}/deliveries` endpoint (verified at `connectors/router.py:298-337`) with cursor-based pagination + filters by status + time range.

- **R6 — `connector_routes` for scope config [RESEARCH-COMPLETE]**: Verified at `connectors/models.py:177-214`. The "scope" step of the 5-step wizard writes to this table per FR-662 step 4. **Resolution**: The wizard's scope step calls `POST /workspaces/{wid}/connectors/{cid}/routes` (existing endpoint at `connectors/router.py:172-237`) with the chosen routes. NO new endpoint needed.

- **R7 — Workspace authorization pattern [RESEARCH-COMPLETE]**: Verified at `workspaces/router.py:92-102` + `workspaces/service.py:289-314`. Pattern: router uses `Depends(get_current_user)`; service `_require_membership(workspace_id, requester_id, min_role)` enforces role hierarchy (`viewer < member < admin < owner`); raises `WorkspaceAuthorizationError` on insufficient role. **Resolution**: All new endpoints follow the same pattern. The `POST /transfer-ownership` requires `WorkspaceRole.owner` (only the current owner can initiate); the consume endpoint validates 2PA token consumption + commits the role swap.

- **R8 — Visibility GET response shape [RESEARCH-COMPLETE]**: Verified at `workspaces/router.py:212-221` + `schemas.py:172-176`. Response: `VisibilityGrantResponse(workspace_id, visibility_agents: list[str], visibility_tools: list[str], updated_at)`. **Resolution**: The visibility explorer page consumes this directly. The XYFlow + Dagre graph builds nodes from `visibility_agents` (one node per FQN) + edges to the workspace itself. NO new aggregator endpoint needed for v1; a future `/visibility/graph` aggregator may add cross-workspace inbound grants if the spec's "grants received" tab requires it.

- **R9 — XYFlow + Dagre graph precedent [RESEARCH-COMPLETE]**: Verified — `apps/web/components/features/discovery/HypothesisNetworkGraph.tsx` (UPD-039 / discovery workbench) + `apps/web/components/features/fleet/FleetTopologyGraph.tsx` (UPD-042 / fleet dashboard) both use `@xyflow/react` + `@dagrejs/dagre`. Pattern: build `nodes: Node<T>[]` + `edges: Edge[]` from data; render within `<ReactFlowProvider><ReactFlow>` with `<MiniMap>`, `<Controls>`, `<Background>`. **Resolution**: New `VisibilityGraph.tsx` component models on the existing precedent. NO Cytoscape per spec correction §5.

- **R10 — Connector dry-run methods [RESEARCH-COMPLETE]**: Verified at `connectors/implementations/slack.py:26-124`. Existing methods: `validate_config`, `normalize_inbound`, `deliver_outbound`, `health_check`. Dry-run capability does NOT exist today. **Resolution**: NEW `async def test_connectivity(self, config, credential_refs) -> TestResult` method added to each of the 4 connector implementations: Slack (uses `auth.test` API — does NOT send messages), Telegram (uses `getMe` API), Email (uses SMTP/IMAP NOOP commands), Webhook (uses HEAD request to webhook URL). Returns `TestResult(success: bool, diagnostic: str, latency_ms: float)`.

- **R11 — Migration sequence [RESEARCH-COMPLETE]**: Verified — latest migration is `070_user_self_service_extensions.py` (UPD-042). UPD-043's migration is `071_workspace_owner_workbench.py`.

- **R12 — Tagging service [RESEARCH-COMPLETE]**: Verified at `apps/control-plane/src/platform/common/tagging/router.py`. Existing endpoints: `GET /api/v1/tags/{tag}/entities`, `GET/POST/DELETE /api/v1/labels`, `GET/POST/PATCH/DELETE /api/v1/saved-views`, admin labels. **Resolution**: The new `/workspaces/[id]/tags/page.tsx` consumes the existing API with workspace_id implicit via `current_user` scope. NO new backend.

- **R13 — Cost governance public surface [RESEARCH-COMPLETE]**: Verified at `apps/control-plane/src/platform/cost_governance/router.py:1-50`. Existing services: `get_anomaly_service`, `get_budget_service`, `get_chargeback_service`, `get_cost_attribution_service`, `get_forecast_service`. **Resolution**: The dashboard's budget gauge reads `WorkspaceBudgetResponse` via the existing `get_budget_service`. NO new endpoint needed.

## Phase 1 — Design Decisions

> Implementation tasks (in tasks.md) MUST honour these decisions or escalate via spec amendment.

### D1 — `WorkspaceSettings` schema extension via 3 JSONB columns

3 NEW JSONB columns on `WorkspaceSettings`: `quota_config: JSONB DEFAULT '{}'`, `dlp_rules: JSONB DEFAULT '{}'`, `residency_config: JSONB DEFAULT '{}'`. Reasoning: column-extension is consistent with the existing `cost_budget: JSONB` pattern + simpler migration than introducing 3 new tables + sufficient for the bounded-cardinality use case (one row per workspace).

### D2 — 2PA primitive is greenfield in this feature

Per spec correction §12 + Rule 33. NEW `two_person_approval/` BC with `TwoPersonApprovalChallenge` model + 3 endpoints. The challenge's `action_payload` is FROZEN at creation time — the consume endpoint executes EXACTLY that payload, NOT a client-resubmitted one (preventing TOCTOU). 5-minute TTL via Redis hash mirror; the database row is the source of truth, Redis is for fast lookup + auto-expiry.

### D3 — 2PA `action_type` enum extensible

Initial enum value: `workspace_transfer_ownership` (UPD-043's only consumer). Extensible by future destructive operations (e.g., `workspace_archive`, `super_admin_password_reset`, `vault_unseal_quorum_share`). Each consumer registers its action type in the enum + provides a handler that consumes the challenge's `action_payload`.

### D4 — `co_signer_id != initiator_id` enforced server-side

Per Rule 33's "two-person" requirement + spec edge case. The `approve` endpoint validates `current_user.id != challenge.initiator_id`; rejects with HTTP 400 + clear error "the co-signer must be a different user". The CI static-analysis check at T032 of UPD-042 (Rule 46 enforcement for `/me/*`) does NOT apply here (these are NOT `/me/*` endpoints).

### D5 — Connector dry-run methods are opaque to the wizard

Each connector implementation's `test_connectivity()` returns a uniform `TestResult(success, diagnostic, latency_ms)` shape. The wizard UI renders the result without knowing connector-specific details. Connector-specific diagnostic text lives in the implementation (e.g., Slack: "auth.test returned ok"; Webhook: "HEAD returned 200").

### D6 — Test-connectivity does NOT persist `outbound_deliveries`

Per User Story 3 acceptance scenario 3 + spec edge case. The dry-run methods invoke connector APIs (Slack `auth.test`, Telegram `getMe`, etc.) but DO NOT write to the `outbound_deliveries` table. This prevents activity-panel pollution from wizard tests.

### D7 — Connector secrets at canonical UPD-040 path

Per spec correction §10. Vault path: `secret/data/musematic/{env}/connectors/workspace-{wid}/{cid}`. The `connectors` domain is canonical per UPD-040 FR-689; `workspace-{wid}/{cid}` is the resource hierarchy. The brownfield's `secret/data/musematic/{env}/workspaces/{id}/connectors/{cid}` is REWRITTEN to fit the canonical scheme.

### D8 — Visibility explorer is read-only in v1

Per User Story 6 + spec correction §6. The graph displays grants given + received but does NOT support inline editing. Editing happens at `/workspaces/{id}/settings` → Visibility tab (existing `PUT /workspaces/{id}/visibility` endpoint). A future enhancement may add inline editing on the graph.

### D9 — IBOR sync-history pagination via cursor

Per FR-664 + research R3. The new `GET /admin/ibor/{id}/sync-history` endpoint exposes the existing `list_sync_runs(connector_id)` method with cursor-based pagination via `(timestamp DESC, id DESC)` composite cursor.

### D10 — IBOR test-connection diagnostic is stepped

Per FR-664 + User Story 5 acceptance scenario 3. The new `POST /admin/ibor/{id}/test-connection` endpoint returns a stepped result: `[{step: "dns_lookup", status: "success", duration_ms: 45}, {step: "tcp_connect", ...}, {step: "tls_handshake", ...}, {step: "ldap_bind", ...}, {step: "sample_query", ...}]`. The UI renders each step with green/red indicators.

### D11 — Workspace dashboard summary endpoint is cached

Per FR-658 + SC-001 (≤ 3 seconds). The aggregator query against multiple BCs (goals + executions + agents + budget + quotas + tags + DLP + audit) is expensive; cached in Redis for 30 seconds (key: `workspace:summary:{workspace_id}`, TTL = 30s). Cache invalidation on any workspace state change via the existing audit-event Kafka subscription.

### D12 — Admin tab `?tab=workspaces` is new; `?tab=ibor` is verified

Per research R2. The existing `AdminSettingsPanel.tsx` tabs array (lines 16-39) does NOT include `workspaces` (verified). It DOES include `oauth` (UPD-041) + `connectors` + `quotas` + others. Whether `ibor` is in the existing array needs verification at T037 — if YES, EXTEND the tab content with new wizard sub-features per FR-664; if NO, ADD a new entry. Either way, the visible UI changes are wizard sub-features.

### D13 — J20 modeled on J04 (Workspace Goal Collaboration)

Per research §17 of spec phase + spec correction §11. J20 is a NEW ~250-line file modeled on the existing J04 (verified at 31,924 bytes — extensive workspace-scoped journey). J20 covers: dashboard load → invite member → add Slack connector → set budget → revoke a session → DSR submission via `/me/dsr`. The `journey_step()` block pattern is consistent with the existing journeys.

### D14 — UPD-039 documentation integration is BEST-EFFORT

Mirrors UPD-040 / UPD-041 / UPD-042 design pattern. If UPD-039 has landed, runbooks + admin-guide updates live in `docs/`; if delayed, they live in `specs/093-workspace-owner-workbench/contracts/` and merge into UPD-039 later.

## Phase 2 — Track A Build Order (Backend additions)

**Days 1-4 (1 dev). Depends on UPD-040 + UPD-041 + UPD-042 being on `main`.**

1. **Day 1 morning** — Pre-flight: confirm UPD-040 + UPD-041 + UPD-042 are merged on `main`; confirm migration sequence is at `070_user_self_service_extensions.py` so `071` is the next slot per research R11.
2. **Day 1 morning** — Author Alembic migration `071_workspace_owner_workbench.py` per design D1: 3 ALTER TABLE statements adding JSONB columns to `workspaces_settings`. CREATE TABLE for `two_person_approval_challenges` per design D2. Reversible downgrade.
3. **Day 1 afternoon** — Modify `workspaces/models.py:208-248`: add 3 new JSONB columns. Author NEW `two_person_approval/models.py` per design D2 + D3.
4. **Day 2 morning** — Author NEW `two_person_approval/service.py` per design D2 + D4 + spec correction §12: atomic state transitions via `SELECT ... FOR UPDATE`; same-actor refusal; 5-minute TTL via Redis hash mirror.
5. **Day 2 afternoon** — Author NEW `two_person_approval/router.py` with 3 endpoints (`/challenges`, `/challenges/{id}/approve`, `/challenges/{id}/consume`); register in `main.py`.
6. **Day 2 afternoon** — Add NEW endpoint `POST /workspaces/{id}/transfer-ownership` per FR-659: handler initiates a 2PA challenge via the new BC; on consume, swaps the workspace `owner_id`. Both `auth.workspace.transfer_initiated` (single-actor, on initiate) and `auth.workspace.transfer_committed` (post-2PA, on consume) audit entries emit per spec correction §10.
7. **Day 3 morning** — Add NEW endpoint `GET /workspaces/{id}/summary` per FR-658 + design D11: aggregator queries goals + executions + agents + budget + quotas + tags + DLP + audit; cached in Redis 30s.
8. **Day 3 afternoon** — Add NEW endpoint `POST /workspaces/{wid}/connectors/{cid}/test-connectivity` per FR-662 + spec correction §6 + design D5 + D6.
9. **Day 3 afternoon** — Add 4 NEW `test_connectivity()` methods to connector implementations per research R10: Slack (auth.test), Telegram (getMe), Email (SMTP NOOP), Webhook (HEAD). Each returns uniform `TestResult` shape per design D5.
10. **Day 4 morning** — Add 3 NEW IBOR admin endpoints per FR-664 + spec correction §13: `POST /admin/ibor/{id}/test-connection` (stepped diagnostic per design D10), `POST /admin/ibor/{id}/sync-now` (delegates to existing `trigger_sync`), `GET /admin/ibor/{id}/sync-history` (cursor pagination per design D9).
11. **Day 4 afternoon** — Wire 9 new audit-event types per spec correction §10 across the relevant services.
12. **Day 4 afternoon** — Author 6 NEW pytest test files (~60 cases total). Each follows the existing pattern (`pytest-asyncio` + injected fixtures).

Day-4 acceptance: `pytest apps/control-plane/tests/{two_person_approval,workspaces,connectors,auth}/` passes (~60 unit tests); the 8 new endpoints + 4 dry-run methods + 9 audit-event types are wired correctly; the migration is reversible; the 2PA primitive enforces atomic state transitions + same-actor refusal + 5-minute TTL.

## Phase 3 — Track B Build Order (Frontend pages)

**Days 1-6 (1-2 devs in parallel; can start day 1 with placeholder Zod schemas).**

13. **Day 1 morning** — Author shared `WorkspaceOwnerLayout.tsx` (sidebar nav for `/workspaces/[id]/*` route group); author API + Zod schema scaffolding (`lib/api/workspace-owner.ts` + `lib/schemas/workspace-owner.ts`) with placeholder schemas mirroring backend Pydantic.
14. **Day 1 afternoon** — Author 5 TanStack Query hooks (`use-workspace-summary`, `use-2pa-challenge`, `use-connector-test-connectivity`, `use-ibor-admin`, etc.).
15. **Day 2** — Author `/workspaces/page.tsx` (workspaces list) + `/workspaces/[id]/page.tsx` (dashboard with 7 cards) per FR-658. Cards: ActiveGoals, ExecutionsInFlight, AgentCount, BudgetGauge (reuses cost_governance per research R13), QuotaUsageBars, TagSummary (UPD-033 reuse), DLPViolationsCount (UPD-076/078 reuse), RecentActivity.
16. **Day 3** — Author `/workspaces/[id]/members/page.tsx` per FR-659: members table, InviteMemberDialog (reuses existing `POST /members` endpoint), TransferOwnershipDialog (NEW — initiates 2PA challenge + displays challenge status).
17. **Day 3** — Author `/workspaces/[id]/settings/page.tsx` per FR-660 with 4 sub-domain forms: BudgetForm (existing cost_budget), QuotaConfigForm (NEW), DLPRulesForm (NEW), ResidencyForm (NEW).
18. **Day 4** — Author `/workspaces/[id]/connectors/page.tsx` (list with workspace-owned badge) + `[connectorId]/page.tsx` (detail) + `ConnectorSetupWizard.tsx` (5-step shared stepper) per FR-661 + FR-662.
19. **Day 4** — Author 4 connector-specific wizard step components: SlackWizardSteps, TelegramWizardSteps, EmailWizardSteps, WebhookWizardSteps. Each calls the new `POST /test-connectivity` endpoint per design D5.
20. **Day 5** — Author `ConnectorActivityPanel.tsx` per FR-663 reading existing `outbound_deliveries` via the existing `/deliveries` endpoint per research R5; author `RotateSecretDialog.tsx` (UPD-040 KV v2 rotation per Rule 44).
21. **Day 5** — Author `/workspaces/[id]/quotas/page.tsx` (quota visualization + edit), `/workspaces/[id]/tags/page.tsx` (workspace tags — UPD-033 reuse per research R12).
22. **Day 5** — Author `/workspaces/[id]/visibility/page.tsx` per FR-665 + spec correction §5 + research R9 (NOT Cytoscape) + design D8: VisibilityGraph.tsx (XYFlow + Dagre modeled on `HypothesisNetworkGraph.tsx`) + GrantDetailPanel.tsx.
23. **Day 6 morning** — Modify `AdminSettingsPanel.tsx` per design D12 + research R2: add 1 new tab `workspaces` to the existing tabs array (lines 16-39); author `WorkspacesTab.tsx` (admin global view) + author IBORConnectorWizard + AttributeMappingWizard + SyncHistoryDrillDown for the IBOR tab content.
24. **Day 6 morning** — i18n integration: extract ~80 new strings to `apps/web/messages/en.json` under hierarchical namespaces; commit with TODO markers for the 5 other locales (vendor-translated per UPD-039 / FR-620).
25. **Day 6 afternoon** — Run `pnpm test:i18n-parity`; verify all 6 locale catalogs have new keys.
26. **Day 6 afternoon** — Run axe-core scan on all 8 new pages + 3 admin tab extensions; verify zero AA violations per Rule 41 inheritance from UPD-083.
27. **Day 6 afternoon** — Run `pnpm test`, `pnpm typecheck`, `pnpm lint` to verify all CI gates pass.
28. **Day 6 afternoon** — Author Playwright E2E `apps/web/tests/e2e/workspace-owner-pages.spec.ts` with ~25 scenarios covering the 8 new pages.

Day-6 acceptance: 8 new pages + 3 admin tab extensions render correctly against the live Track A backend; `pnpm test`, `pnpm typecheck`, axe-core scan, i18n parity check all pass; Playwright E2E ~25 scenarios pass.

## Phase 4 — Track C Build Order (E2E + journey)

**Days 4-6 (1 dev — depends on Track A endpoints functional + Track B pages reachable).**

29. **Day 4 afternoon** — Create `tests/e2e/suites/workspace_owner/__init__.py` + `conftest.py` (NEW pytest fixtures: workspace-with-seeded-data, workspace-with-connectors, multi-member workspace).
30. **Day 5** — Author 7 E2E test files (one per User Story 1-4 + 6 + 2PA primitive). Each file has 4-6 test functions; total ~560 lines.
31. **Day 6 morning** — Create `tests/e2e/journeys/test_j20_workspace_owner.py` per FR-666 + design D13. Modeled on J04. ~250 lines covering 18 sequential `journey_step()` blocks: dashboard load → invite member → add Slack connector → 5-step wizard → test-connectivity → set budget → revoke session → DSR submission → ownership transfer with 2PA.
32. **Day 6 afternoon** — Modify `tests/e2e/journeys/test_j01_admin_bootstrap.py`: add 2 new steps covering the IBOR admin wizard (test-connection + sync-now). ~30 lines addition.
33. **Day 6 afternoon** — Modify `.github/workflows/ci.yml`: add `tests/e2e/suites/workspace_owner/` to UPD-040's matrix-CI test path (3 modes: mock / kubernetes / vault).

Day-6 acceptance: 7 E2E test files + J20 + J01 extension all pass; matrix CI green for all 3 secret modes.

## Phase 5 — Cross-Cutting Verification

**Day 7 (1 dev).**

34. **Day 7 morning** — Run the canonical secret-leak regex set against `kubectl logs platform-control-plane-...` for 24 hours of synthetic load (connector test-connectivity + IBOR test-connection + ownership transfer flows) per Rule 31; verify zero matches.
35. **Day 7 morning** — Run UPD-040's `scripts/check-secret-access.py` extended for any new code paths; verify zero violations.
36. **Day 7 afternoon** — Verify all 8 new endpoints emit audit-chain entries per Rule 9: synthetic test asserts `audit_chain_entries` row count grows by exactly 1 per state-changing call.
37. **Day 7 afternoon** — Verify Rule 33's 2PA invariants: test-1 — same-actor approval rejected per design D4; test-2 — challenge expires after 5 minutes; test-3 — `consume` endpoint executes the FROZEN action_payload (TOCTOU prevention).

## Phase 6 — SC verification + documentation polish

**Days 7-9 (1 dev — overlaps Phase 5).**

38. **Day 7-8** — Run the full SC verification sweep per the spec's 20 SCs. Capture verification record at `specs/093-workspace-owner-workbench/contracts/sc-verification.md` (NEW file).
39. **Day 8 morning** — Author operator runbooks per design D14: `docs/operator-guide/runbooks/workspace-owner-2pa.md` (the 2PA flow), `docs/operator-guide/runbooks/connector-self-service-troubleshooting.md`, `docs/operator-guide/runbooks/ibor-connector-test-connection.md`.
40. **Day 8 afternoon** — Modify admin guide: add a "Workspace Owner Surfaces" section explaining the workspace-owner role + admin equivalents at `/admin/settings?tab=workspaces`.
41. **Day 9** — Modify release notes: add UPD-043 entry covering 8 new pages + 5 new endpoints + 2PA primitive (foundational — reusable by future destructive ops) + 4 connector dry-run methods.
42. **Day 9** — Final review pass; address PR feedback; merge.

## Effort & Wave

**Total estimated effort: 11-13 dev-days** (5-6 wall-clock days with 3 devs in parallel: 1 on Track A, 1-2 on Track B, 1 on Track C; convergent on Days 7-9).

The brownfield's "6 days (6 points)" understates by ~50% (consistent with v1.3.0 cohort pattern):
- The foundational 2PA primitive (greenfield per Rule 33) adds ~2 dev-days the brownfield doesn't account for.
- The 4 connector implementations needing new `test_connectivity()` methods add ~1 dev-day per research R10 — does NOT exist today.
- The 3 NEW JSONB columns + Alembic migration + Pydantic schema validators add ~0.5 day.
- The 9 new audit-event types add ~0.5 day.
- The 6 i18n catalogs × 80 entries add ~0.5 day.
- The J20 creation as a fresh ~250-line test file modeled on J04 adds ~1 day vs the brownfield's implicit "extend J01" framing.

**Wave: Wave 18 — last in the v1.3.0 audit-pass cohort.** Position in execution order:
- Wave 11 — UPD-036 Administrator Workbench
- Wave 12 — UPD-037 Public Signup Flow
- Wave 13 — UPD-038 Multilingual README
- Wave 14 — UPD-039 Documentation Site
- Wave 15 — UPD-040 HashiCorp Vault Integration
- Wave 16 — UPD-041 OAuth Env-Var Bootstrap
- Wave 17 — UPD-042 User-Facing Notification Center
- **Wave 18 — UPD-043 Workspace Owner Workbench** (this feature)

**Cross-feature dependency map**:
- UPD-043 INTEGRATES with UPD-036 (admin tab pattern reuse).
- UPD-043 INTEGRATES with UPD-040 (Vault canonical scheme + matrix-CI inheritance).
- UPD-043 INTEGRATES with UPD-042 (shared UX patterns + 2PA UI dialog inspiration).
- UPD-043 INTRODUCES the foundational 2PA primitive (reusable by future destructive ops in UPD-086+).
- UPD-043 EXTENDS UPD-027 / UPD-079 (cost governance for budget gauge).
- UPD-043 EXTENDS UPD-033 (tags at workspace scope).
- UPD-043 EXTENDS UPD-077 (multi-channel notifications for invitation emails).

## Risk Assessment

**Medium risk overall.** UPD-043 has the largest UI surface in the v1.3.0 cohort + introduces foundational 2PA infrastructure. Risks:

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **R1: 2PA primitive design too narrow** | Medium | High (rework if future destructive ops can't reuse) | Per design D3 — extensible `action_type` enum + frozen `action_payload` JSONB. Future consumers register their action type + handler. |
| **R2: 2PA TOCTOU vulnerability** | Low | High (security) | Per design D2 + Rule 33 — server-side atomic state transitions via `SELECT FOR UPDATE`; the `consume` endpoint executes the FROZEN action_payload, NOT a client-resubmitted one. |
| **R3: 2PA same-actor approval bypass** | Low | High (security) | Per design D4 — server-side validation `current_user.id != challenge.initiator_id`; rejects with HTTP 400. Tested in T037. |
| **R4: Connector test-connectivity sends user-visible message** | Medium | Medium (UX) | Per design D5 + D6 + research R10 — each connector implementation uses connector-specific dry-run paths (Slack `auth.test`, Telegram `getMe`, etc.) — NOT message-write APIs. Tested in T029. |
| **R5: Workspace authorization escalation (member → owner)** | Low | High (security) | Per research R7 — existing `_require_membership` enforces role hierarchy. The new transfer-ownership endpoint requires `WorkspaceRole.owner` (current owner only initiates). |
| **R6: Visibility graph performance with 500+ nodes** | Medium | Low (UX) | Per spec SC-014 — XYFlow + Dagre handles ≤ 500 nodes in ≤ 1 second; for larger graphs, the page lazy-loads + paginates. |
| **R7: Admin tab `?tab=ibor` in existing array uncertain** | Medium | Low (1-line code change) | Per design D12 + research R2 — verified at T037 of tasks; if absent, ADD the entry; if present, EXTEND the content. |
| **R8: Connector dry-run race with concurrent saves** | Low | Low (test-only) | Test-connectivity does NOT persist per design D6; concurrent saves are unaffected. |
| **R9: Workspace summary endpoint slow under load** | Medium | Medium (UX — dashboard slow) | Per design D11 — Redis cache 30s; SC-001 verifies ≤ 3s. |
| **R10: i18n catalog drift across 6 locales** | Medium | Low (untranslated strings) | UPD-088's parity check catches drift; 7-day grace window applies. |

## Plan-correction notes (vs. brownfield input)

1. **Effort estimate corrected from 6 days to 11-13 dev-days** (consistent with v1.3.0 cohort pattern).
2. **Wave 18 reaffirmed** (last in cohort).
3. **Connectors are ALREADY workspace-scoped** per spec correction §3 + research R10. The brownfield's premise that UPD-043 introduces "workspace-owned" connectors is INCORRECT.
4. **14 workspace-scoped connector endpoints ALREADY EXIST** per spec correction §5. Brownfield's "Backend workspace-owned connector model with scoping" step is rephrased as "add 1 new test-connectivity endpoint to the existing 14".
5. **Admin pages are TABS, not standalone routes** per spec correction §8. Brownfield's `/admin/ibor/new` standalone route is REWRITTEN as a wizard sub-feature in the existing IBOR tab.
6. **Cytoscape does NOT exist** per spec correction §5 + research R9. Brownfield's "Cytoscape-based graph rendering" is REWRITTEN as XYFlow + Dagre per the existing precedent.
7. **2PA infrastructure is GREENFIELD** per spec correction §12 + Rule 33. Brownfield's "Ownership transfer flow with 2PA integration" understates the scope — the primitive must be built from scratch.
8. **Vault path corrected** per spec correction §10. Brownfield's `secret/data/musematic/{env}/workspaces/{id}/connectors/{cid}` is REWRITTEN to `secret/data/musematic/{env}/connectors/workspace-{wid}/{cid}` per UPD-040 canonical scheme.
9. **Connector dry-run methods are NEW** per research R10. The 4 connector implementations need new `test_connectivity()` methods.
10. **`WorkspaceSettings` schema extension** per spec correction §1 + research R1. 3 NEW JSONB columns required.
11. **Migration `071`** per research R11. UPD-040/041/042 own 069-070.
12. **J20 must be CREATED** per spec correction §11 + research §17. Modeled on J04.
13. **9 new audit-event types** per spec correction §10. Following existing `auth.workspace.*` convention.
14. **Test-connectivity does NOT persist outbound_deliveries** per design D6. Avoids activity-panel pollution.

## Complexity Tracking

| Area | Complexity | Why |
|---|---|---|
| `WorkspaceSettings` schema extension | Low | 3 JSONB columns; backward-compat defaults. |
| Workspace summary aggregator endpoint | Medium | Cross-BC aggregation + Redis cache + invalidation hooks. |
| 2PA primitive | High | Greenfield; atomic state transitions; TOCTOU prevention; same-actor refusal; TTL via Redis mirror; extensible `action_type` enum. |
| Connector dry-run methods | Medium | 4 connector-specific implementations + uniform `TestResult` shape. |
| IBOR admin endpoints | Medium | 3 endpoints; stepped diagnostic; sync-now delegation. |
| 8 new Next.js pages | High | ~2000 lines of TSX + ~30 sub-components + i18n × 6 locales + Playwright × 25 scenarios. |
| Visibility explorer (XYFlow + Dagre) | Medium | Modeled on existing precedent; ≤ 500 nodes performance constraint. |
| 7 E2E test files + J20 + J01 extension | Medium | One per User Story; conftest fixtures reused. |
| i18n + axe-core sweep | Medium | 480 entries × 6 locales + AA scan on 11 surfaces. |

**Net complexity: medium-high.** The 2PA primitive is the highest-risk piece (foundational; reusable; security-critical); once it ships, the rest is mechanical.
