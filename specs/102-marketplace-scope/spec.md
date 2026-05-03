# Feature Specification: UPD-049 — Marketplace Scope (Workspace, Tenant, Public Default Tenant)

**Feature Branch**: `102-marketplace-scope`
**Spec Directory**: `specs/102-marketplace-scope/`
**Created**: 2026-05-03
**Status**: Draft
**Input**: User description: "UPD-049 — Marketplace Scope (Workspace, Tenant, Public Default Tenant)"

---

## Brownfield Context

**Prior work**: `specs/099-marketplace-scope/` (merged via PR #133) introduced the marketplace scope dimension and the `agents_visibility` RLS policy. UPD-049 is implemented in production for the `registry_agent_profiles` surface as of 2026-05-03. This spec is a **refresh pass** to consolidate UPD-049 acceptance criteria as a self-contained, testable specification, and to capture follow-on requirements that surfaced during the 099 implementation (notably: rejection-reason notifications via UPD-042, fork-update notifications via UPD-044 template-update channel, and reviewer assignment for queue load balancing).

**FR coverage**: FR-733 through FR-741 (functional-requirements section 122).

**Scope boundary**: This feature covers marketplace scope, the platform-staff review workflow for public submissions, the per-tenant `consume_public_marketplace` feature flag, and the fork-into-private-tenant action. It does NOT redefine the underlying agent registry (FR-234–241), nor the broader template fork mechanism introduced in UPD-044, nor the contract-template surface they govern.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Default-tenant creator publishes an agent to the public hub (Priority: P1)

A creator working in a workspace inside the platform's default (SaaS) tenant has built an agent that they believe is broadly useful. They want it discoverable by every default-tenant user without granting any cross-workspace data access.

**Why this priority**: Without this story, the public-hub value proposition does not exist. It establishes the marketplace's defining characteristic — a curated, platform-staff-reviewed pool of agents discoverable across all default-tenant workspaces — and is the gating dependency for stories 3 and 5.

**Independent Test**: A default-tenant creator opens the publish flow for an agent they own, picks the public scope, supplies the required marketing metadata, and submits. The agent transitions to `pending_review`. A platform-staff reviewer opens the review queue, sees the submission, approves it, and the agent transitions to `published` and becomes visible in the marketplace browse surface to a second default-tenant user in a different workspace.

**Acceptance Scenarios**:

1. **Given** a creator in the default tenant viewing an agent they own, **When** they open the publish flow, **Then** the scope picker offers three options: workspace-only, tenant-wide, and public default-tenant.
2. **Given** the creator selects the public default-tenant scope, **When** the publish form is rendered, **Then** the form requires a marketing description, a category, and at least one tag in addition to the fields required for the lower scopes.
3. **Given** the creator submits the public-scope publish form, **When** the submission is accepted, **Then** the agent's review status transitions to `pending_review`, the submission appears in the platform-staff review queue, and an audit chain entry records the transition.
4. **Given** a platform-staff reviewer opens an item in the review queue, **When** they approve it, **Then** the agent's review status transitions to `published`, an audit chain entry records the approval and the reviewer identity, and the agent becomes visible in the marketplace browse surface to all default-tenant users.
5. **Given** a platform-staff reviewer rejects the submission with a reason, **When** the rejection is recorded, **Then** the submitter is notified through the user notification channel and the agent returns to `draft` (or the prior state) with the review notes attached.

---

### User Story 2 — Enterprise-tenant user is prevented from publishing publicly (Priority: P1)

A user in an Enterprise tenant (e.g., Acme) builds an agent and reaches the publish flow. Enterprise tenants do not share data with other tenants and therefore cannot publish into the cross-tenant public hub. The product surface and the API both refuse the action; the refusal is unambiguous and gives the user a path forward (publish workspace-wide or tenant-wide).

**Why this priority**: This story is what makes the multi-tenant architecture safe. Without enforcement, a single misclick from an Enterprise user could leak Enterprise IP into the public hub. It is co-equal P1 with story 1 because the public hub cannot exist without this guarantee.

**Independent Test**: An Enterprise-tenant user opens the publish flow. The public-scope option is visible but disabled with an explanation of why; the workspace-only and tenant-wide options remain enabled. A separate API-level test posts a publish request with public scope as an Enterprise user and receives an HTTP 403 response with a stable, machine-readable error code identifying tenant-kind as the reason.

**Acceptance Scenarios**:

1. **Given** an Enterprise-tenant user opens the publish flow, **When** the scope picker is rendered, **Then** the public default-tenant option is shown but disabled, with a visible explanation that public publishing is only available to creators in the platform's default (SaaS) tenant.
2. **Given** an Enterprise-tenant user submits a publish request with public scope to the API, **When** the request reaches the publish endpoint, **Then** the API returns HTTP 403 with an error code identifying tenant-kind as the reason, no state change is persisted, and the refusal is recorded in the tenant audit chain.
3. **Given** the same Enterprise-tenant user picks the workspace-only or tenant-wide scope, **When** they submit, **Then** the publish proceeds normally and no review queue entry is created.

---

### User Story 3 — Enterprise tenant with consume flag sees public agents (Priority: P2)

A platform-staff administrator enables `consume_public_marketplace` for the Acme Enterprise tenant under contract. Acme users now see public default-tenant agents alongside their tenant-scoped agents in the marketplace browse surface, can run them, and the running cost is attributed to Acme.

**Why this priority**: This is the monetisation lever for Enterprise contracts that opt into the public catalogue. Story 1 must exist before this is meaningful; story 2 must exist before this is safe. Inside-tenant browsing of Acme's own agents works without this flag, so this is P2 rather than P1.

**Independent Test**: A platform-staff admin sets `consume_public_marketplace=true` for the Acme tenant via the tenant feature-flag surface. An Acme user (in any workspace) opens the marketplace and sees a merged list: Acme's tenant-scoped agents plus all currently-published public default-tenant agents. The public agents are visually labelled as originating from the public marketplace. The Acme user runs one and the resulting cost event is attributed to the Acme tenant.

**Acceptance Scenarios**:

1. **Given** a platform-staff admin enables the consume flag for a tenant, **When** the change is saved, **Then** an audit chain entry records the flag transition with the admin's identity and the contract reference.
2. **Given** the Acme tenant has the consume flag enabled, **When** an Acme user opens the marketplace browse surface, **Then** the result set includes both Acme's tenant-scoped agents and currently-published public default-tenant agents.
3. **Given** the merged result set is rendered, **When** an Acme user looks at an individual agent card, **Then** public-origin agents are clearly labelled as "From public marketplace" (or equivalent) and tenant-scoped agents are not.
4. **Given** an Acme user invokes a public agent, **When** the execution completes, **Then** the cost event is attributed to the Acme tenant (the consumer), not the originating tenant.
5. **Given** an Acme user opens a public agent, **When** they view the agent's edit affordances, **Then** edit actions on the original public agent are unavailable; only Run, Inspect, and Fork are available.

---

### User Story 4 — Enterprise tenant without consume flag sees only its own agents (Priority: P2)

A different Enterprise tenant (Globex) has not opted into the consume flag. Globex users see only Globex's tenant-scoped and workspace-only agents in the marketplace; the public hub is invisible to them, with no leakage of public-hub existence in result counts, search hints, or telemetry.

**Why this priority**: This is the negative-case complement of story 3 and the privacy guarantee for Enterprise tenants who haven't paid for or contracted into the public catalogue. Co-priority with story 3.

**Independent Test**: A Globex tenant user opens the marketplace and submits a search whose terms match a published public default-tenant agent. The result set contains only Globex agents matching those terms. Result counts, "did you mean" hints, and analytics do not reveal that the public hub contains matching items.

**Acceptance Scenarios**:

1. **Given** a Globex tenant user opens the marketplace browse surface, **When** the result set is rendered, **Then** it contains only agents whose tenant_id is Globex (regardless of marketplace scope within Globex).
2. **Given** a Globex user runs a search with terms that would match published public agents, **When** the search returns, **Then** the result set, the result count, and any search analytics do not surface or count those public agents.
3. **Given** a Globex user attempts to access a public agent by its identifier directly, **When** the request reaches the API, **Then** the response is the same 404-equivalent that would be returned for any non-existent or inaccessible agent — i.e., no information leak that the agent exists elsewhere.

---

### User Story 5 — Forking a public agent into a private tenant (Priority: P2)

An Acme user (with the consume flag enabled) finds a useful public agent and wants to customise it without publishing changes back to the public catalogue. They Fork the agent. A new agent record is created inside Acme's tenant with provenance pointing at the original. The fork is editable, private to Acme, and stays unaffected by future updates to the original.

**Why this priority**: Forking unlocks the customisation use case Enterprise tenants typically need before adopting a public agent. Without it, consumption is read-only and adoption stalls. Co-priority with stories 3–4.

**Independent Test**: An Acme user opens a public agent and clicks Fork. They are prompted to choose the destination scope (workspace-only or tenant-wide). The fork completes; the new agent appears under Acme's owned agents with a provenance link to the original. The user edits the fork and the original public agent's content is unchanged. Later, the original's author publishes a new version; the fork is unaffected, but the Acme user receives a notification per the UPD-044 template-update channel.

**Acceptance Scenarios**:

1. **Given** an Acme user views a public agent, **When** they trigger the Fork action, **Then** a destination scope picker appears offering workspace-only or tenant-wide (public is not offered).
2. **Given** the user confirms a destination scope, **When** the fork operation completes, **Then** a new agent record is created in the Acme tenant at the chosen scope, with provenance metadata referencing the original public agent.
3. **Given** the fork exists, **When** the user edits it, **Then** edits affect only the fork; the original public agent's data is unchanged.
4. **Given** the original public agent's owner publishes a new version, **When** the new version is approved and published, **Then** existing forks are not auto-updated, and each fork owner receives a notification via the UPD-044 template-update channel.

---

### Edge Cases

- **Public agent updated after first approval**: when a publisher submits a new version of an already-published public agent, the new version enters `pending_review`; the previously-approved version stays `published` and visible in the marketplace until the new version is approved or rejected.
- **Public agent deprecated by author**: a deprecated public agent disappears from marketplace browse and search, but remains visible to existing forks (so fork owners can read the original's lineage) and to anyone holding a direct identifier reference.
- **Reviewer rejects with reason**: the rejection reason is delivered to the submitter through the user notification channel (UPD-042). The submission record retains the rejection notes for audit.
- **Submission queue load**: when the review queue grows beyond the capacity of a single platform-staff member, queue items can be assigned to specific reviewers (one of several platform staff). Assignment is recorded in the audit chain.
- **Public agent depends on a tool unavailable to a consumer tenant**: when an Acme user runs a public agent that invokes a tool not registered in Acme's tenant, the run fails with an error that explicitly names the missing tool dependency and points the user toward registering the tool or forking-and-modifying.
- **Consume flag toggled off while Acme users have active public-agent runs**: in-flight runs complete normally and are attributed to Acme; new browse/search results no longer include public agents from the moment the flag is disabled.
- **Default-tenant author tries to publish an agent that has unresolved required dependencies**: the publish flow refuses with a clear list of missing dependencies; no `pending_review` state is created.
- **Reviewer attempts to approve their own submission**: the system prevents a reviewer from acting on a submission they authored; the action is not available in the queue UI and is rejected at the API.

---

## Requirements *(mandatory)*

### Functional Requirements

**Marketplace scope dimension**

- **FR-733**: The system MUST support three marketplace scopes for any registered agent: workspace-only (visible only inside the publishing workspace), tenant-wide (visible to every workspace inside the publishing tenant), and public default-tenant (visible across the platform's default SaaS tenant subject to review).
- **FR-734**: The system MUST default a new agent's scope to workspace-only.
- **FR-735**: An agent's scope MUST be changeable only by users with publish permission on that agent inside the owning tenant.

**Public-scope publishing & review**

- **FR-736**: The system MUST require additional metadata (marketing description, category, at least one tag) before accepting a public-scope publish submission.
- **FR-737**: The system MUST transition a public-scope submission into a `pending_review` state visible only to platform-staff reviewers and the submitter.
- **FR-738**: The system MUST provide a platform-staff review queue that lists pending-review submissions, supports assigning a submission to a specific reviewer, and supports approve and reject actions with required reviewer notes.
- **FR-739**: An approval MUST transition the agent to `published` and make it visible across the default tenant; a rejection MUST return the agent to a non-public state with the reviewer's notes attached.
- **FR-740**: The system MUST emit an audit-chain entry for each scope change, submission, assignment, approval, rejection, deprecation, and consume-flag toggle, including the actor identity and timestamp.

**Tenant-kind enforcement**

- **FR-741**: The system MUST refuse — at both UI surface and API — any attempt by a user in an Enterprise-kind tenant to publish at the public default-tenant scope, returning a stable, machine-readable refusal code that names tenant-kind as the reason.

**Consume flag & visibility**

- **FR-741.1**: The system MUST honour a per-tenant `consume_public_marketplace` feature flag. When set, an Enterprise tenant's marketplace browse and search results MUST include currently-published public default-tenant agents in addition to the tenant's own agents. When unset, public agents MUST NOT be visible, MUST NOT be counted, and MUST NOT leak through search hints, suggestions, or analytics.
- **FR-741.2**: The system MUST visually distinguish public-origin agents from tenant-owned agents in browse and detail surfaces.
- **FR-741.3**: For an Enterprise consumer of a public agent, edit affordances on the original MUST be unavailable; only Run, Inspect, and Fork MUST be available.
- **FR-741.4**: Cost events generated by an Enterprise tenant invoking a public agent MUST be attributed to the consuming Enterprise tenant, not the publishing tenant.

**Forking**

- **FR-741.5**: Users with consume access to a public agent MUST be able to Fork it into their own tenant at workspace-only or tenant-wide scope (never public).
- **FR-741.6**: A forked agent MUST persist provenance referencing the originating public agent.
- **FR-741.7**: Forks MUST NOT auto-propagate when the originating public agent updates; instead, fork owners MUST receive a notification via the template-update channel established by UPD-044.

**Notifications & audit**

- **FR-741.8**: Reviewer rejection reasons MUST be delivered to the submitter through the user notification channel established by UPD-042.
- **FR-741.9**: Reviewers MUST NOT be able to act on submissions they themselves authored; the system MUST enforce this both in the UI and at the API.

**Information non-leakage**

- **FR-741.10**: When a tenant lacks the consume flag, attempting to access a public agent by its direct identifier MUST return the same not-found response the system returns for any inaccessible agent — i.e., the existence of the public-hub agent must not be inferable from response shape, error code, or response timing.

### Key Entities *(include if feature involves data)*

- **Agent (extended)**: A registered agent that now carries (1) a marketplace scope (workspace / tenant / public default-tenant), (2) a review status (draft / pending_review / approved / rejected / published / deprecated), (3) reviewer identity and review notes once a review action has occurred, and (4) optional provenance pointing at an originating public agent if it is a fork.
- **Tenant (extended)**: A tenant now carries a kind (default / enterprise) and a feature-flag set including `consume_public_marketplace`. Tenant kind governs whether the tenant can publish to the public scope; the consume flag governs whether the tenant can see and run public-scope agents.
- **Marketplace Review Submission (logical view)**: A logical projection over agents in `pending_review` state, displayed to platform-staff reviewers as a queue with assignment, approval, and rejection actions. Carries reviewer notes and assignment history.
- **Audit Chain Entry**: A tamper-evident log entry recording each scope change, submission transition, reviewer action, fork creation, and consume-flag toggle, with actor, timestamp, and prior/next state.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A creator in the default tenant can move an agent from draft to publicly visible in the marketplace within one approve action by platform staff. End-to-end median wall time from submission to platform-staff approve action MUST be observable and reportable.
- **SC-002**: 100% of attempts by Enterprise-tenant users to publish at the public scope are refused, both via UI and via direct API call, with a stable refusal code that operations can alert on.
- **SC-003**: When the consume flag is enabled for a tenant, that tenant's users see at least the union of (their tenant's agents) ∪ (currently-published public default-tenant agents) in marketplace browse — measurable by comparing the result count before and after the flag is toggled, on identical query inputs.
- **SC-004**: When the consume flag is disabled, no information about public-hub agents leaks into a tenant — measurable by a parity test that, for the same query terms, the result count, suggestions, and analytics events are identical between (a) a fresh Enterprise tenant with no consume flag and (b) the same tenant after a public agent matching those terms is published. The two MUST be indistinguishable.
- **SC-005**: Cost events generated when a consuming tenant runs a public agent are attributed 100% to the consumer; cross-tenant cost attribution defects in this surface MUST be zero in production billing reports.
- **SC-006**: Forking a public agent into a private tenant produces a working, editable copy in under 5 seconds of wall time at the 95th percentile, with provenance correctly linked.
- **SC-007**: Reviewers receive their assigned queue items in under 2 seconds at the 95th percentile, and the queue UI surfaces unassigned items separately from assigned items so platform staff can self-balance.
- **SC-008**: Submitters receive rejection-reason notifications within 60 seconds at the 95th percentile of the reviewer recording the rejection.
- **SC-009**: J25 — the Marketplace Multi-Scope end-to-end journey covering all five user stories — passes on every CI run.

---

## Assumptions

- **Tenancy primitives are in place.** UPD-046 and UPD-047 (tenant architecture and the default-tenant signup flow, specs `096-tenant-architecture` and `098-default-tenant-signup`) provide the `tenant_kind` column and tenant feature-flag bag this feature depends on. This spec does not redefine those primitives.
- **Notification channels are in place.** UPD-042 (user notifications) and UPD-044 (template-update notifications) are assumed available for the rejection-reason and fork-update notification paths respectively; this spec does not redesign them.
- **Audit chain is in place.** The existing audit-chain mechanism handles tamper-evident event logging; this feature adds new entry kinds but does not redefine the chain itself.
- **Platform-staff identity already exists.** The platform-staff role and its admin-workbench surface (UPD-040, spec `086-administrator-workbench-and`) are the access basis for the review queue. No new privileged role is introduced.
- **Cost attribution machinery already attributes per-tenant.** The cost-governance subsystem (UPD-031, spec `079-cost-governance-chargeback`) already records the consuming tenant on each execution; this feature requires that the consumer tenant remains the attributed party even when the agent's owning tenant is the default tenant.
- **Search and browse surfaces are unified for visibility filtering.** Marketplace browse and full-text search both flow through the same visibility-filter layer, so a single change to that layer is sufficient to enforce non-leakage when the consume flag is unset.
- **The previously-merged 099-marketplace-scope work is the baseline.** This spec treats `099-marketplace-scope` (PR #133) as the baseline implementation. Refresh items captured here include reviewer-assignment for queue load, rejection-reason notifications via UPD-042, fork-update notifications via UPD-044, and explicit non-leakage guarantees (FR-741.10 / SC-004).
- **English-only initial UX for review queue.** The platform-staff review surface ships in English first; localisation follows the broader UPD-035 i18n plan (spec `083-accessibility-i18n`).
- **Pricing/contract enforcement of the consume flag is out of scope.** Whether a tenant is *entitled* to have the consume flag enabled (per its plan or contract) is governed by UPD-029 (plans, subscriptions, quotas — spec `097-plans-subscriptions-quotas`); this feature implements only the technical effect of the flag.
