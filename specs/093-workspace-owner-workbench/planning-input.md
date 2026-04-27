# UPD-043 — Workspace Owner Workbench and Connector Self-Service

## Brownfield Context

**Current state (verified in repo):**
- Backend `workspaces/router.py` fully implemented (create, update, delete, members, quotas, visibility).
- Backend `connectors/implementations/{slack,telegram,email,webhook}.py` functional connectors; `connectors/router.py` exposes CRUD.
- Backend `auth/ibor_service.py` + `ibor_sync.py` with LDAP/OIDC/SCIM already wired.
- UI has `/admin/settings/page.tsx` minimal admin-scoped view. UPD-036 adds `/admin/workspaces` and `/admin/connectors` and `/admin/ibor` globally for super admin/admin.

**Gaps:**
1. **No workspace-owner scope UI** — only admin sees workspaces globally. A workspace owner has NO dashboard for THEIR workspace (members, budget, quotas, visibility grants, DLP rules at workspace scope).
2. **No workspace-owned connectors distinction** — today connectors are platform-owned only (admin configures). A workspace owner cannot set up their own Slack/Telegram/Email/Webhook scoped to their team.
3. **No connector setup wizards** — connector configuration is raw API; no guided flow, no test-connectivity, no scope configuration.
4. **Thin IBOR admin page** — UPD-036 lists it but only as basic CRUD; no connection-test flow, no attribute-mapping wizard, no sync-history drill-down.
5. **No visibility explorer** — the zero-trust visibility model (FR-002) is invisible to owners; they can't see what their workspace can access or what accesses them.

**Extends:**
- UPD-027 Cost Governance (workspace budget primitive).
- UPD-033 Tags, Labels, Saved Views (tags at workspace scope).
- UPD-036 Administrator Workbench (admin equivalents exist).
- UPD-040 Vault Integration (workspace-owned connector secrets live in Vault).

**FRs:** FR-658 through FR-666 (section 116).

---

## Summary

UPD-043 introduces the **workspace owner** as a first-class role with their own dedicated workbench, distinct from the platform administrator. The feature:

- Creates `/workspaces/{id}` as a full-featured dashboard scoped to the workspace.
- Adds pages for members, settings, connectors (workspace-owned), visibility explorer.
- Distinguishes **workspace-owned** vs **platform-owned** connectors; owners configure their own Slack/Telegram/Email/Webhook.
- Adds guided setup wizards for every connector type with test-connectivity and audit.
- Upgrades the admin IBOR page with connection tests, mapping wizards, and sync drill-down.
- Introduces a visibility explorer that surfaces the zero-trust model comprehensibly.

---

## User Scenarios

### User Story 1 — Workspace owner reviews their workspace (Priority: P1)

A workspace owner logs in to see the current state of their team's work.

**Independent Test:** Open `/workspaces/{id}`. See active goals, executions in flight, agent count, budget gauge, quota usage, recent activity. All data scoped to this workspace only.

**Acceptance:**
1. Dashboard loads in under 3s with real data for the workspace.
2. Budget gauge shows consumption with forecast (reuses UPD-027 primitives scoped to workspace).
3. Quota usage per resource (agents, fleets, executions, storage) with color-coded thresholds.
4. Tag summary and DLP violations count.
5. Recent audit activity scoped to the workspace.
6. No data from other workspaces visible.
7. Owner without visibility grants from external resources sees only their own.

### User Story 2 — Workspace owner invites a new member (Priority: P1)

A workspace owner invites a new team member and assigns them a role.

**Independent Test:** Open members page. Invite by email or select existing user. Assign role. Member receives email invitation; accepts; appears in member list.

**Acceptance:**
1. `/workspaces/{id}/members` lists current members with role + joined date + recent activity link.
2. Invite form accepts email or searches existing users.
3. Role picker shows: owner, admin, member, viewer with descriptions.
4. Invitation email delivered via UPD-028 channels.
5. On acceptance, user appears in list; audit entry emitted.
6. Transfer ownership action requires 2PA per FR-561 and FR-559.
7. Remove member action removes access and audits.

### User Story 3 — Workspace owner configures Slack for their team (Priority: P1)

A workspace owner wants agents in their workspace to post to a specific Slack channel.

**Independent Test:** Navigate to `/workspaces/{id}/connectors`. Click "Add Slack connector". Follow wizard: prerequisites check, credentials, test connectivity, scope to which agents, activate. Agent executions post to Slack.

**Acceptance:**
1. Connectors page clearly distinguishes workspace-owned vs platform-owned.
2. Add connector wizard guides through 5 steps: prerequisites / credentials / test / scope / activate.
3. Credentials stored in Vault at `secret/data/musematic/{env}/workspaces/{id}/connectors/{cid}`.
4. Test connectivity attempts real connection without sending user-visible messages.
5. Scope config: which agents / fleets / events trigger the connector.
6. Activity log shows deliveries with success/failure counts 24h / 7d.
7. Rotate credentials action writes new Vault version with dual-credential window.

### User Story 4 — Workspace owner sets budget with hard cap (Priority: P2)

A workspace owner sets a monthly $500 budget with hard cap at 100%.

**Independent Test:** Navigate to `/workspaces/{id}/settings`. Set budget; save. Trigger executions that cross 50% / 80% thresholds; verify alerts. Cross 100%; verify executions blocked.

**Acceptance:**
1. Settings page exposes budget + hard cap controls.
2. Soft thresholds (50%, 80%) trigger alerts per FR-503 (UPD-027).
3. Hard cap at 100% blocks new executions with clear error.
4. Admin override mechanism available per FR-503.
5. Forecast visible for end-of-period spend with confidence interval.
6. Changes emit audit chain entry.

### User Story 5 — Admin configures a new LDAP connector with test (Priority: P2)

A super admin wants to add a corporate LDAP for user sync.

**Independent Test:** Navigate to `/admin/ibor`. Add new LDAP connector. Test connection with diagnostics (DNS / TLS / bind / sample query). Configure attribute mapping. Schedule sync. Run manual sync. Review results.

**Acceptance:**
1. IBOR admin page shows existing connectors with status.
2. Add connector wizard guides through: connector type / connection params / test / attribute mapping / sync schedule / scope / activate.
3. Test connection shows step-by-step diagnostics and outcome.
4. Attribute mapping wizard maps external attributes to platform fields.
5. Sync history shows per-sync metrics and errors.
6. Error detail drill-down links to Loki logs.

### User Story 6 — Workspace owner explores visibility graph (Priority: P3)

A workspace owner wonders what other workspaces their agents can see.

**Independent Test:** Navigate to `/workspaces/{id}/visibility`. See graph of grants given and received. Filter. Audit recent grants.

**Acceptance:**
1. Visibility graph shows workspace's agents, their visible agents/tools, source of visibility (direct grant, pattern match, workspace-level default).
2. Grants given and received tabs.
3. Audit trail of visibility changes.
4. Graph is performant for up to 500 nodes.
5. Zero-trust defaults clearly visualized.

---

### Edge Cases

- **Owner without visibility grants**: dashboard still loads; visibility-dependent metrics show zero without confusion.
- **Member removed mid-execution**: their in-flight executions continue; they lose read access on completion.
- **Ownership transfer while member invitation pending**: invitation stays valid; new owner sees it.
- **Workspace archive with active executions**: typed confirmation warns about blocked executions; option to cancel them first.
- **Connector credentials invalid**: connector disabled automatically; alert to owner; agents fall back to alternative connectors or emit attention request.
- **Connector rate-limited by third party (Slack 429)**: activity log surfaces with retry counts; alerts operator.
- **LDAP connector times out**: sync record shows timeout error with link to relevant Loki logs.

---

## UI Routes (Next.js)

```
apps/web/app/(main)/
├── workspaces/
│   ├── page.tsx                               # NEW: list of workspaces user owns/belongs to
│   └── [id]/
│       ├── page.tsx                           # NEW: dashboard
│       ├── members/page.tsx                   # NEW
│       ├── settings/page.tsx                  # NEW
│       ├── connectors/
│       │   ├── page.tsx                       # NEW: list + add
│       │   └── [connectorId]/page.tsx         # NEW: detail with activity + rotate
│       ├── visibility/page.tsx                # NEW: visibility explorer
│       ├── quotas/page.tsx                    # NEW
│       └── tags/page.tsx                      # NEW: workspace-level tags
```

```
apps/web/app/(admin)/ibor/
├── page.tsx                                   # EXISTING from UPD-036, extended
├── [connectorId]/page.tsx                     # NEW: detail with mapping wizard + sync
└── new/page.tsx                               # NEW: wizard for add
```

## Shared Components

- `<WorkspaceOwnerLayout>` — left sidebar with workspace navigation
- `<WorkspaceMembersTable>` — reusable member list with role management
- `<ConnectorSetupWizard>` — 5-step stepper shared for all connector types
- `<ConnectorActivityPanel>` — activity log + diagnostics
- `<IBORConnectorWizard>` — LDAP/OIDC/SCIM guided setup
- `<AttributeMappingWizard>` — source → platform field mapper
- `<VisibilityGraph>` — graph rendering using existing Cytoscape integration from discovery workbench
- `<BudgetGauge>` — reusable budget visualization (lift from UPD-027 admin cost page)
- `<QuotaUsageBars>` — per-resource quota bars

## Backend Additions

Existing backend largely sufficient. Minor additions:
- `GET /api/v1/workspaces/{id}/summary` — aggregated dashboard data (counts, gauges).
- `GET /api/v1/workspaces/{id}/members` / `POST` (invite) / `PATCH /{member_id}` / `DELETE /{member_id}`.
- `POST /api/v1/workspaces/{id}/transfer-ownership` (requires 2PA).
- `GET /api/v1/workspaces/{id}/connectors` / `POST` / `DELETE /{cid}`.
- `POST /api/v1/workspaces/{id}/connectors/{cid}/test-connectivity`.
- `POST /api/v1/workspaces/{id}/connectors/{cid}/rotate-secret`.
- `GET /api/v1/workspaces/{id}/visibility` — aggregated visibility graph data.
- Extend IBOR router with: `POST /api/v1/admin/ibor/{connector_id}/test-connection`, `GET /api/v1/admin/ibor/{connector_id}/sync-history`, `POST /api/v1/admin/ibor/{connector_id}/sync-now`.

## Acceptance Criteria

- [ ] `/workspaces/{id}` dashboard renders for owner with real data
- [ ] Members CRUD + role assignment + ownership transfer functional
- [ ] Ownership transfer requires 2PA per FR-561
- [ ] Settings page allows budget, hard cap, DLP, residency config
- [ ] Workspace-owned connectors clearly distinguished from platform-owned
- [ ] Setup wizard for each connector type (Slack, Telegram, Email, Webhook)
- [ ] Test-connectivity works without sending user-visible messages
- [ ] Connector credentials in Vault at canonical workspace-scoped path
- [ ] Activity panel shows delivery metrics and failures
- [ ] IBOR admin wizard for LDAP/OIDC/SCIM with test + mapping + sync history
- [ ] Visibility explorer graph renders correctly with grants given/received
- [ ] All new pages pass axe-core AA
- [ ] All new pages localized in 6 languages
- [ ] New J20 Workspace Owner journey passes end-to-end
