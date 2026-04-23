# Feature Specification: IBOR Integration and Agent Decommissioning

**Feature Branch**: `056-ibor-agent-decommissioning`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "Integrate with enterprise IBOR (LDAP/AD/Keycloak/Okta) for agent identity sync. Add formal agent decommissioning lifecycle."

**Scope note**: The platform has a role-based access control engine (`auth/rbac.py` with `UserRole`, `RolePermission`, and a `RBACEngine` that checks workspace-scoped permissions) and an agent registry (`registry/models.py` with `AgentProfile`, `LifecycleStatus` enum covering `draft | validated | published | disabled | deprecated | archived`). Neither integrates with enterprise identity systems today — role assignments are created manually through the platform's admin API, and there is no mechanism to import identity facts from an external directory. The registry's `LifecycleStatus` enum ends at `archived`, which is a soft-delete marker rather than a formal end-of-life state — there is no operational contract around what happens to running instances, discovery visibility, or re-activation when an agent reaches end of life.

This feature delivers two related but independently shippable capabilities:

1. **Enterprise identity broker (IBOR) sync** — A configurable connector that imports user-to-role and agent-role assignments from an enterprise identity system (LDAP/AD, OIDC/Keycloak, SCIM/Okta) into the platform's RBAC store on a scheduled cadence. Supports both pull (IBOR → platform) and push (platform → IBOR for compliance reporting) modes.
2. **Formal agent decommissioning** — A new lifecycle terminal state `decommissioned` with an operational contract: running instances are shut down, the agent is removed from marketplace/discovery surfaces, execution and audit history are preserved, and re-activation requires an explicit re-registration flow rather than a status toggle.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Enterprise identity sync imports user-role mappings (Priority: P1)

An enterprise operator configures an IBOR connector (LDAP, OIDC, or SCIM) with connection details and a role-mapping policy. On a configured cadence (or via on-demand trigger), the platform pulls user membership + role assignments from the directory and reconciles them with the platform's RBAC store. Users whose directory group membership changes get their platform roles updated automatically on the next sync cycle.

**Why this priority**: Enterprise customers adopting the platform already manage user identities in LDAP/AD/Keycloak/Okta. Without IBOR sync, every user-role assignment must be re-created manually in the platform — a non-starter for organizations with hundreds of users and quarterly access reviews. This is the gating requirement for enterprise adoption.

**Independent Test**: Configure an IBOR connector against a test OIDC provider; create 3 test users with different group memberships; trigger a sync; verify that each user now has the corresponding platform roles. Remove a user from a directory group; trigger sync; verify the platform role was revoked.

**Acceptance Scenarios**:

1. **Given** an IBOR connector is configured and a mapping policy maps directory group `Platform-Admins` to platform role `platform_admin`, **When** a sync run imports a user who is a member of `Platform-Admins`, **Then** that user is granted the `platform_admin` role in the platform's RBAC store on the next workspace they access.
2. **Given** an IBOR-sourced role assignment exists for a user, **When** that user is removed from the source directory group, **Then** the next sync run revokes the platform role assignment and emits an audit event.
3. **Given** a sync run begins, **When** a subset of users fails to sync (e.g., one user's email does not match a platform account), **Then** the remaining users sync successfully, failures are reported with per-user reasons, and the overall run completes with a partial-success status.
4. **Given** an operator triggers a manual sync, **When** the sync completes, **Then** the result carries counts of `users_created`, `users_updated`, `roles_added`, `roles_revoked`, `errors` so the operator can validate the outcome.

---

### User Story 2 — Platform-initiated identity push to IBOR for audit (Priority: P2)

A compliance officer needs a single source of truth in the enterprise IBOR for which service accounts (agents) exist in the platform, which roles they carry, and when they were decommissioned. The platform pushes agent identity records to the IBOR on a scheduled cadence so the enterprise's access-review reports include agent service accounts automatically.

**Why this priority**: Push-mode complements pull by closing the compliance loop: enterprises can run a single quarterly access review in their IBOR and have full coverage of platform agents. Without push, agents are invisible to enterprise access reviews and compliance teams maintain a separate spreadsheet.

**Independent Test**: Configure an IBOR push connector with credentials for a test SCIM endpoint; register a new agent with roles `[executor, observer]`; trigger a push; verify a corresponding service-account record appears in the test SCIM endpoint with the same roles. Decommission the agent; trigger push; verify the SCIM record is marked inactive.

**Acceptance Scenarios**:

1. **Given** a push connector is configured, **When** a sync run executes, **Then** every active agent in the platform has a corresponding record in the IBOR with matching roles and status.
2. **Given** an agent is decommissioned, **When** the next push sync runs, **Then** the corresponding IBOR record is marked inactive (or equivalent per the target IBOR's convention) within the same sync cycle.
3. **Given** the IBOR is temporarily unreachable, **When** a push sync attempt fails, **Then** the failure is recorded, retried with backoff, and surfaced in the operator dashboard; the next successful attempt reconciles all pending changes.

---

### User Story 3 — Formal agent decommissioning with history preservation (Priority: P1)

A workspace owner or platform admin needs to take an agent out of service permanently — not just disable it for a week. The operator invokes a decommission action with a mandatory reason (regulatory, business, security). The platform shuts down all running instances, removes the agent from the marketplace and discovery surfaces, marks the agent record as `decommissioned` with the timestamp and reason, and preserves all execution history, audit records, and trust certifications for compliance retention.

**Why this priority**: The existing `archived` status is a soft-delete flag with no operational semantics — it does not guarantee instance shutdown, does not remove from discovery, and gives no audit trail for *why* the agent was removed. Regulated customers need a formal terminal state with auditable intent and a clean shutdown contract. This is the gating requirement for customers with regulatory retention obligations.

**Independent Test**: Register an agent; launch 2 instances; publish it to the marketplace. Invoke decommission with reason "regulatory retirement". Verify: (a) both instances were shut down within the shutdown SLO; (b) the agent no longer appears in marketplace search; (c) the agent's `status` is `decommissioned`, `decommissioned_at` is set, `decommission_reason` contains "regulatory retirement"; (d) prior execution records for the agent are still queryable via the audit API.

**Acceptance Scenarios**:

1. **Given** an agent with 2 running instances is selected for decommissioning, **When** the owner invokes the decommission action with a reason, **Then** both instances are stopped, the agent status is set to `decommissioned`, `decommissioned_at` is recorded, the reason is persisted, and an audit event is emitted.
2. **Given** a decommissioned agent, **When** any user searches the marketplace, browses discovery, or selects agents for a new workflow, **Then** the decommissioned agent does not appear in any of those surfaces.
3. **Given** a decommissioned agent, **When** a compliance officer queries audit or execution history for that agent's prior work, **Then** all historical records remain fully queryable and exportable; no data is deleted.
4. **Given** a decommission attempt is initiated without a reason, **When** the action is validated, **Then** the action is rejected with a message requiring a non-empty reason (minimum 10 characters, bounded maximum).
5. **Given** a decommission is invoked by a user without `workspace_owner` or `platform_admin` role, **When** permission is checked, **Then** the action is denied with a 403-equivalent authorization error.

---

### User Story 4 — Re-activation requires explicit re-registration (Priority: P1)

A decommissioned agent cannot be "un-decommissioned" by a status flip. If the business needs the agent back, the operator must complete the standard agent registration flow, which generates a new agent record with a new identifier. The old decommissioned record remains in place as historical evidence; it is never mutated back into an active state.

**Why this priority**: Without this constraint, decommissioning is just a reversible status toggle and loses its compliance value. Regulated customers rely on the immutability of the terminal state — a decommissioned audit entry from March cannot silently become an active agent in June, or trust/audit chains break.

**Independent Test**: Decommission an agent. Attempt to set its status back to `published` via the status-transition API; verify the transition is rejected. Invoke the standard "register new agent" flow with the same name/namespace; verify a new agent record is created with a new id, and the old decommissioned record is unchanged.

**Acceptance Scenarios**:

1. **Given** an agent is in `decommissioned` status, **When** any status-transition request attempts to move it to `published`, `disabled`, `deprecated`, or any other non-terminal state, **Then** the transition is rejected with a message indicating that decommissioning is terminal.
2. **Given** a decommissioned agent with FQN `workspace/namespace/agent-name`, **When** the owner creates a new agent with the same FQN, **Then** a fresh agent record is created with a new id; the old record is retained; the FQN is now associated with the new active agent while the historical FQN-to-record mapping remains intact for audit queries.
3. **Given** a decommissioned agent's state is queried, **When** the response is inspected, **Then** the `decommissioned_at` timestamp and `decommission_reason` are always present; they cannot be cleared or overwritten.

---

### User Story 5 — Decommissioned agents invisible across user-facing discovery (Priority: P2)

A decommissioned agent is structurally excluded from every surface where a user could select or invoke it: marketplace search results, recommended-agent carousels, workflow-builder agent pickers, fleet composition screens, and conversation invocations. It remains visible only in audit/history views and in the platform admin's view for retention-verification purposes.

**Why this priority**: US3 covers the action; US5 covers the consistent application of the invisibility contract across all surfaces. Missing a surface defeats the purpose — if a workflow builder can still select a decommissioned agent, the compliance guarantee is broken.

**Independent Test**: Decommission an agent. Call each discovery surface in turn (marketplace search, agent detail by FQN, workflow-builder agent list, fleet composition list, recommendations carousel). For each surface, verify the decommissioned agent does not appear. For audit/admin views, verify it does appear and its decommissioned state is clearly marked.

**Acceptance Scenarios**:

1. **Given** a decommissioned agent exists, **When** a user searches the marketplace for any matching term, **Then** the agent is excluded from search results regardless of relevance score.
2. **Given** a decommissioned agent's FQN is known, **When** a user navigates directly to the agent's marketplace detail URL, **Then** the response indicates the agent is decommissioned and does not offer invocation controls.
3. **Given** a user composes a new workflow or fleet, **When** the agent picker is opened, **Then** decommissioned agents are not listed.
4. **Given** an audit query targets historical executions, **When** results include executions that ran before decommissioning, **Then** those executions remain fully queryable and the agent reference resolves to a "decommissioned" display state for context.

---

### Edge Cases

- A sync run is triggered while a previous sync is still in progress → the new trigger waits or is rejected with a "sync in progress" message; concurrent runs never corrupt the RBAC store.
- An IBOR connector's credentials expire → the next sync attempt fails with a clear "authentication failed" operator-visible error; partial state from prior syncs is not rolled back.
- A user is in the enterprise directory but has no corresponding platform account → the sync creates a disabled placeholder account or reports the mismatch (depending on operator-configured "auto-provision" policy).
- An agent is mid-execution when decommission is invoked → running executions are allowed to finish (no forced step abort); new instances cannot start; the operator sees a "decommission pending: N in-flight executions" status until the last execution completes.
- The same FQN is reused after decommissioning, then the new agent is also decommissioned → both historical records remain queryable and distinguishable by `decommissioned_at`; the FQN's current association is cleared until a third registration reuses it.
- The IBOR push target's rate limit is hit mid-sync → the sync pauses with exponential backoff; if limits persist beyond a configured retry budget, the run completes with a partial-success status identifying unpushed records.
- A platform admin attempts to decommission an agent already in `decommissioned` status → the action is idempotent and returns a success response without altering `decommissioned_at` or `decommission_reason`.
- An IBOR connector is deleted while historical sync events reference it → the events retain the former connector name for audit; new sync attempts via the deleted connector fail with a clear "connector not configured" error.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The platform MUST allow an admin to create, update, disable, and delete IBOR connector configurations. Each connector specifies a source type (LDAP/AD, OIDC, SCIM), connection details, an authentication credential reference, a sync mode (pull, push, or both), a sync cadence, and a role-mapping policy.
- **FR-002**: In pull mode, a sync run MUST import user membership and group-to-role mappings from the configured source; the outcome MUST include per-user results (`created`, `updated`, `revoked`, `skipped`, `error`) and an overall run summary.
- **FR-003**: Pull sync MUST revoke a platform role assignment when the source no longer lists the user in the corresponding group, provided the assignment was created by this connector (assignments created manually by admins are not touched).
- **FR-004**: In push mode, a sync run MUST export the current list of platform agents (service accounts) with their role assignments and active/decommissioned status to the configured target, using the target's native identity representation where available (e.g., SCIM User or Group).
- **FR-005**: Sync runs MUST be triggerable on a schedule (configured cadence) AND on-demand by an authorized operator; on-demand triggers while a sync is in progress MUST be safely queued or rejected, never cause concurrent mutation.
- **FR-006**: Every sync run MUST produce an audit record including `connector_id`, `mode`, `started_at`, `finished_at`, `counts`, `errors[]`, and retain it for the platform's standard audit retention period.
- **FR-007**: The platform MUST add a new terminal lifecycle state `decommissioned` to the existing agent lifecycle enum. The state is additive; existing states remain unchanged and existing agents are unaffected.
- **FR-008**: Decommissioning MUST record `decommissioned_at` (timestamp) and `decommission_reason` (non-empty text, minimum 10 characters, maximum 2000 characters) on the agent record.
- **FR-009**: Invoking decommission MUST be restricted to users holding `workspace_owner` on the agent's workspace OR `platform_admin`; all other callers receive an authorization denial.
- **FR-010**: Decommissioning MUST trigger shutdown of all running instances of the agent; in-flight executions MAY complete, but no new instances MAY be launched from the moment the decommission is recorded.
- **FR-011**: A decommissioned agent MUST be structurally excluded from: (a) marketplace search results, (b) agent recommendations, (c) workflow-builder agent pickers, (d) fleet composition pickers, (e) conversation/attention routing targets.
- **FR-012**: A decommissioned agent MUST remain queryable via audit/history APIs so prior executions, trust certifications, policy evaluations, and cost records continue to resolve the agent reference and display it in a clearly-marked "decommissioned" context.
- **FR-013**: A decommissioned agent's status MUST NOT be transitionable back to any active state. The only way to restore functionality is the standard agent registration flow, which creates a new agent record with a new identifier.
- **FR-014**: The agent registration flow MUST permit reuse of the FQN of a decommissioned agent; when reused, the new agent record MUST receive a new identifier and MUST NOT inherit trust certifications, policy attachments, or role assignments from the decommissioned record.
- **FR-015**: Every decommission action and every IBOR sync run MUST emit a domain event to the platform audit event stream for downstream consumption by analytics, alerts, and compliance pipelines.
- **FR-016**: IBOR connectors that handle credentials MUST store only a reference to the credential; the credential value itself MUST never be stored in plaintext in the connector configuration or returned in any API response.
- **FR-017**: When an IBOR sync fails partially, the run MUST complete with a `partial_success` status; the system MUST NOT roll back already-applied changes solely because later changes failed.
- **FR-018**: The platform MUST expose operator-facing visibility into sync run history and decommission events with at least the 90 most-recent runs/events queryable without pagination and older history available via paginated query.
- **FR-019**: Behavior when no IBOR connector is configured MUST be identical to the pre-feature state: role assignments are created and maintained manually; no sync runs occur; no import/export events are emitted.
- **FR-020**: Behavior when no agents are decommissioned MUST be identical to the pre-feature state: the existing lifecycle states continue to work unchanged; marketplace, discovery, and workflow-builder surfaces behave as they did before.

### Key Entities

- **IBOR Connector**: A persistent configuration record describing a single enterprise directory integration. Fields: `id`, `name`, `source_type`, `sync_mode`, `cadence`, `credential_ref`, `role_mapping_policy`, `enabled`, `created_by`, `created_at`, `last_run_at`, `last_run_status`.
- **Role Mapping Policy**: An ordered list of rules mapping a directory construct (group DN, OIDC claim value, SCIM group ref) to a platform role plus an optional workspace scope. Policies are owned by a connector; the same role can be produced by multiple policies.
- **Sync Run Record**: An audit entry for one execution of an IBOR sync. Fields: `id`, `connector_id`, `mode`, `started_at`, `finished_at`, `status` (in one of: running, succeeded, partial_success, failed), `counts` (users_created, users_updated, roles_added, roles_revoked, errors), `error_details`, `triggered_by`.
- **IBOR-Sourced Role Assignment**: A user-role record that carries a `source_connector_id` reference, distinguishing it from manually-created assignments. Revocation during sync applies only to these; manual assignments are preserved.
- **Agent Decommission Record**: A structural extension of the existing agent profile entity: `decommissioned_at` (timestamp, null until terminal), `decommission_reason` (text, non-empty when terminal), `decommissioned_by` (user id). Cannot be cleared once set.
- **Decommission Event**: An audit event emitted at the moment of decommissioning, carrying `agent_id`, `agent_fqn`, `workspace_id`, `decommissioned_at`, `decommission_reason`, `decommissioned_by`, `active_instance_count_at_decommission`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An enterprise customer with 500 users and 50 directory groups can complete an initial IBOR pull sync in under 5 minutes, with 100% of eligible user-role mappings applied.
- **SC-002**: Subsequent incremental pull syncs (only changed users/groups) complete within 60 seconds for the same 500-user population.
- **SC-003**: A platform admin can identify the status of the most recent sync run for any connector within 30 seconds using the operator dashboard.
- **SC-004**: Decommissioning an agent with up to 5 running instances completes (status set, instances stopped, discovery exclusion applied) within 60 seconds end-to-end at p95.
- **SC-005**: 100% of decommissioned agents are absent from marketplace search, agent recommendations, and workflow-builder pickers within 60 seconds of the decommission timestamp.
- **SC-006**: 100% of historical executions, trust certifications, and cost records for decommissioned agents remain queryable indefinitely after decommissioning, with no data loss.
- **SC-007**: Zero occurrences of a decommissioned agent transitioning back to an active status outside of the explicit re-registration flow, verified across an automated test suite that exercises every known status-transition path.
- **SC-008**: With no IBOR connector configured AND no agents decommissioned, the existing test suite passes unmodified and platform behavior is unchanged from the pre-feature baseline (FR-019 + FR-020).

---

## Assumptions

- The platform already has an RBAC engine (`RBACEngine` in `auth/rbac.py`) with `UserRole` and `RolePermission` tables; IBOR-sourced assignments extend this engine rather than replace it.
- The existing `LifecycleStatus` enum in `registry/models.py` covers `draft | validated | published | disabled | deprecated | archived`; `decommissioned` is added as a new terminal value beyond these (Brownfield Rule 6 — additive).
- The existing `AgentProfile` entity in `registry/models.py` is the record that gains the `decommissioned_at`, `decommission_reason`, and `decommissioned_by` fields (Brownfield Rule 7 — all new fields nullable/defaulted to preserve backward compatibility).
- Shutdown of running agent instances on decommission is delegated to the existing Runtime Controller shutdown RPC; this feature does not re-implement instance lifecycle.
- Marketplace, discovery, and workflow-builder surfaces already filter by `LifecycleStatus`; the invisibility contract for `decommissioned` is achieved by extending the existing filter predicates (exclude `decommissioned` and `archived` alike from user-facing surfaces).
- IBOR connectors supporting LDAP, OIDC, and SCIM cover the majority of enterprise deployments (AD via LDAP; Keycloak via OIDC; Okta via OIDC or SCIM); additional source types can be added later via the same connector abstraction.
- Credentials for IBOR connectors are stored using the platform's existing secret-reference convention (connector configuration holds only a reference; the secret value is resolved at sync time via the platform's secret store integration).
- Decommissioning is an irreversible terminal state by policy — this is a deliberate constraint, not a technical limitation. Business flexibility to bring an agent back is preserved via the "register as new agent" flow (FR-014).
- The "register new agent with same FQN" flow (FR-014) is handled by the existing agent registration API; no new registration surface is introduced by this feature.
- Sync cadence defaults to hourly for pull and daily for push; operators can override per-connector.
- Role mapping policies are evaluated deterministically: the first matching rule in the policy list wins; later rules are skipped. This matches the evaluation semantics of the existing `RBACEngine`.
