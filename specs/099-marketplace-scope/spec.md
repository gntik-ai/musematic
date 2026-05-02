# Feature Specification: UPD-049 — Marketplace Scope (Workspace, Tenant, Public Default Tenant)

**Feature Branch**: `100-upd-049-marketplace`
**Spec Directory**: `specs/099-marketplace-scope/`
**Created**: 2026-05-02
**Status**: Draft
**Input**: User description (UPD-049 brownfield input — marketplace scope dimension introducing three scopes [`workspace`, `tenant`, `public_default_tenant`], a per-Enterprise-tenant `consume_public_marketplace` feature flag, platform-staff review for public submissions, and fork operation for cross-tenant reuse)

## Summary

UPD-049 introduces a marketplace **scope dimension** on every published agent so that
discoverability is no longer all-or-nothing within a tenant. Three scopes are supported:

- `workspace` — visible only inside the publishing workspace (the default).
- `tenant` — visible to every workspace inside the publishing tenant.
- `public_default_tenant` — visible to every user of the **default** tenant (the SaaS public hub),
  and visible read-only to Enterprise tenants who have opted in via the
  `consume_public_marketplace` feature flag.

Public publishing is reserved to the default tenant: an Enterprise tenant cannot expose its
agents to other Enterprise tenants. This is the SaaS hub-and-spoke model — Enterprise tenants
are spokes that may consume the public hub but never become publishers to it. Publishing to
public scope requires platform-staff review (app-store style); a submission moves through
`pending_review → approved → published` (or `rejected`). Approved-and-deprecated public
agents continue to work for existing forks but disappear from search.

A fork operation lets a consumer copy a public agent into their own tenant or workspace,
breaking the link from upstream so subsequent edits stay private. Forks track provenance via
`forked_from_agent_id` and the source owner is notified when a fork happens (per UPD-044
template-update notification semantics).

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Default-tenant creator publishes agent to public marketplace (Priority: P1)

A Pro user inside the default tenant has built a useful agent and wants every default-tenant
user — and any opted-in Enterprise tenant — to discover and run it.

**Why this priority**: This is the primary new capability of the feature. Without it the
public marketplace remains theoretical; with it the SaaS public hub becomes populated by
real creator output and the rest of the value chain (consumption, forking, review) follows.

**Independent Test**: A default-tenant user opens the publish flow on an agent they own,
selects scope `public_default_tenant`, fills the marketing metadata (category, marketing
description, tags), and submits. The submission moves to `pending_review`. A super admin
opens the marketplace-review queue, opens the submission, and approves it. The agent now
appears in the public marketplace listings to a second default-tenant user. Audit-chain
entries exist for submission, approval, and publication.

**Acceptance Scenarios**:

1. **Given** the user is in the default tenant and owns an agent in `validated` lifecycle state,
   **When** they open the publish flow,
   **Then** the scope picker shows three options (`workspace`, `tenant`, `public_default_tenant`)
   with no option disabled.
2. **Given** the user selects `public_default_tenant`,
   **When** the publish form renders,
   **Then** a marketing-metadata block becomes mandatory (category from a curated list,
   marketing description, tags).
3. **Given** the user submits with all required fields,
   **When** the request lands at the registry,
   **Then** the agent's `review_status` transitions to `pending_review`, an audit-chain
   entry records the submission, and a `marketplace.submitted` event is published.
4. **Given** the agent is in `pending_review`,
   **When** a super admin opens the review queue,
   **Then** the submission appears with submitter identity, marketing description, and
   submission timestamp.
5. **Given** the super admin reviews and approves,
   **When** approval is recorded,
   **Then** `review_status` transitions to `published`, `reviewed_at` and `reviewed_by_user_id`
   are persisted, an audit-chain entry is recorded, and a `marketplace.approved` followed by
   `marketplace.published` event is published.
6. **Given** the agent is `published` with public scope,
   **When** another default-tenant user opens the marketplace search,
   **Then** the agent is visible in the result set.

### User Story 2 — Enterprise tenant cannot publish to public scope (Priority: P1)

An employee of tenant Acme tries to publish a private internal agent publicly.

**Why this priority**: This is the data-isolation guarantee that makes Enterprise tenants
viable on the same platform as the public hub. A leak here would mean an Enterprise tenant's
proprietary agent (and any prompts / knowledge it carries) becomes visible to other
Enterprise tenants. The refusal must be defense-in-depth (UI + service + database).

**Independent Test**: An Acme-tenant user opens the publish flow on an agent they own and
inspects the scope picker. The `public_default_tenant` option is disabled with a tooltip
"Public publishing is only available in the SaaS public tenant." A direct API call from
the same Acme user with `scope=public_default_tenant` returns HTTP 403 with code
`public_scope_not_allowed_for_enterprise`. A direct database INSERT from an Acme connection
trying to set `marketplace_scope='public_default_tenant'` is refused by a check constraint.

**Acceptance Scenarios**:

1. **Given** the user is in an Enterprise tenant,
   **When** the publish flow renders,
   **Then** the `public_default_tenant` option is disabled with an explanatory tooltip.
2. **Given** the same user bypasses the UI and calls the publish API with
   `scope=public_default_tenant`,
   **When** the request is processed,
   **Then** the API responds 403 with code `public_scope_not_allowed_for_enterprise`.
3. **Given** a malicious or buggy backend call attempts to insert directly,
   **When** the row would be written,
   **Then** the database CHECK constraint refuses the row.

### User Story 3 — Enterprise tenant with consume flag sees public marketplace (Priority: P2)

A super admin enables `consume_public_marketplace=true` for tenant Acme per a signed
contract addendum. Acme users now see the public marketplace alongside their tenant-scoped
agents.

**Why this priority**: This is how the SaaS hub becomes valuable to Enterprise customers —
they can use vetted public agents without the agents leaving Acme's runtime trust
boundary. Cost attribution stays with the consumer.

**Independent Test**: A super admin opens `/admin/tenants/acme` and toggles
`consume_public_marketplace=true`. An audit-chain entry and a `tenants.feature_flag_changed`
Kafka event are recorded. An Acme-tenant user reloads the marketplace page and sees a
merged listing: Acme tenant-scoped agents plus public-scoped agents marked "From public
marketplace". The Acme user runs a public agent; the execution is attributed to Acme's
billing.

**Acceptance Scenarios**:

1. **Given** the super admin sets the flag,
   **When** the change is persisted,
   **Then** an audit-chain entry and a `tenants.feature_flag_changed` event are recorded
   and the tenant resolver cache is invalidated for that tenant.
2. **Given** an Acme user opens the marketplace,
   **When** the listing renders,
   **Then** public-scope agents appear alongside Acme's tenant-scope agents and are clearly
   labelled.
3. **Given** an Acme user runs a public agent,
   **When** the run is metered,
   **Then** the cost-attribution row is owned by Acme.

### User Story 4 — Enterprise tenant without consume flag is fully isolated (Priority: P2)

A second Enterprise tenant Globex does not have the consume flag set.

**Why this priority**: The default-deny stance must hold absolutely. A Globex user must
not learn that the public marketplace exists, must not see public listings, must not be
able to run public agents.

**Independent Test**: A Globex user opens the marketplace and sees only Globex
tenant-scoped agents. A direct API call to fetch a known public agent's detail page
returns 404. The marketplace search response payload contains no public-scope rows.

**Acceptance Scenarios**:

1. **Given** Globex has the consume flag disabled (or unset),
   **When** a Globex user opens the marketplace,
   **Then** no public-scope agents appear in the result set.
2. **Given** a Globex user crafts a direct request for a public agent's detail page,
   **When** the registry serves the request,
   **Then** the response is 404 (existence is hidden).

### User Story 5 — Forking a public agent into a private tenant (Priority: P2)

An Acme user (with consume flag) finds a useful public agent and wants to customize it
for Acme's specific data, prompts, and policies.

**Why this priority**: Forking is the safety valve that lets consumers benefit from public
work without inheriting future upstream changes (which might violate Acme's policies or
compliance posture). It also creates the provenance graph that lets the source creator
see adoption.

**Independent Test**: The Acme user opens a public agent's detail page, clicks "Fork to
my tenant", chooses Acme's tenant scope and a fresh `local_name`. A new agent record is
created in Acme with `forked_from_agent_id` pointing at the source. The fork is editable
in Acme. The original public agent is unchanged. A later update to the source produces
a notification to the Acme fork owner saying the source has changed and the fork has
NOT been auto-updated.

**Acceptance Scenarios**:

1. **Given** an Acme user fires the fork action against a published public agent,
   **When** the fork API handles the request,
   **Then** a new agent profile is created inside Acme with `forked_from_agent_id` set,
   `marketplace_scope` reset to the consumer's choice (workspace or tenant), and
   `review_status='draft'`.
2. **Given** the fork is created,
   **When** Acme inspects audit chain and Kafka,
   **Then** a `marketplace.forked` event and a hash-linked audit chain entry exist on
   Acme's tenant.
3. **Given** the source agent is later updated and re-approved,
   **When** the platform's notification fan-out runs,
   **Then** every fork owner receives a `marketplace.source_updated` notification stating
   that the source changed and that the fork has NOT been auto-updated.

### Edge Cases

- **Public source updated after publication**: a creator submits a new version of a public
  agent. The new version goes through review again as `pending_review`. The previously
  published version remains visible until the new version is approved, at which point the
  new version replaces it as the canonical published version (single published-version
  invariant per agent).
- **Public agent deprecated by the creator**: existing forks continue to work, the agent
  disappears from public search results, and a deprecation notice is shown to anyone who
  navigates directly to its detail page.
- **Reviewer rejects a submission**: a rejection reason is required and is delivered to
  the submitter via the existing notification path (UPD-042 alert delivery).
- **Submission queue grows large**: super admins can claim submissions optimistically so
  the same submission isn't reviewed twice; an unclaimed-only filter and a reviewer filter
  both exist on the queue.
- **Consumer's tenant lacks a tool the public agent needs**: when the consumer attempts
  to run the agent (or the fork), the runtime raises a clear "tool dependency missing"
  error naming the specific tool — the marketplace listing surface itself doesn't break.
- **Submitter publishes the same agent under a different scope after rejection**: rejection
  is final for that submission; submitter can re-submit a fresh request after addressing
  the rejection reason. Submission rate limit (5/day per submitter) prevents abuse.

## Requirements *(mandatory)*

### Functional Requirements

#### Scope dimension

- **FR-001**: Every agent profile MUST carry a `marketplace_scope` value of one of
  `workspace` (default), `tenant`, or `public_default_tenant`. New agents start at
  `workspace`.
- **FR-002**: Every agent profile MUST carry a `review_status` value of one of `draft`
  (default), `pending_review`, `approved`, `rejected`, `published`, or `deprecated`.
- **FR-003**: An agent's `marketplace_scope` and `review_status` MUST be queryable
  efficiently — the review queue, marketplace listing, and tenant-scoped browse all
  filter on these columns.

#### Publishing flow

- **FR-004**: The publish endpoint MUST accept a `scope` parameter. When `scope` is
  `workspace` or `tenant`, the agent transitions directly to `published` (today's
  behaviour, scope-aware).
- **FR-005**: When `scope=public_default_tenant`, the publish endpoint MUST require a
  marketing-metadata block (`category`, `marketing_description`, `tags`) and MUST refuse
  the request if any of those fields is missing.
- **FR-006**: When `scope=public_default_tenant`, the publish endpoint MUST refuse the
  request with HTTP 403 if the requesting tenant is NOT the default tenant.
- **FR-007**: The marketing `category` MUST be drawn from a platform-curated list (the
  list lives in code and is mirrored to the frontend constants module).
- **FR-008**: A successful public submission MUST set `review_status='pending_review'`,
  record an audit-chain entry, and publish a `marketplace.submitted` Kafka event.
- **FR-009**: A submitter MUST NOT be able to issue more than 5 public submissions per
  rolling 24-hour window. The 6th attempt MUST be refused with HTTP 429 and a
  `Retry-After` header.

#### Three-layer Enterprise refusal

- **FR-010**: The publish UI MUST disable the `public_default_tenant` option for
  Enterprise tenants and surface an explanatory tooltip.
- **FR-011**: The publish service MUST refuse `scope=public_default_tenant` for any
  request originating from a non-default tenant, returning HTTP 403 with code
  `public_scope_not_allowed_for_enterprise`.
- **FR-012**: A database CHECK constraint MUST refuse any row whose
  `marketplace_scope='public_default_tenant'` and whose `tenant_id` is not the
  well-known default-tenant identifier.

#### Review queue

- **FR-013**: A platform-staff queue MUST list all submissions with
  `review_status='pending_review'` cross-tenant. The queue is owned by super admins and
  platform-staff roles and reads via the BYPASSRLS pool.
- **FR-014**: A reviewer MUST be able to claim a submission. Claim is idempotent for the
  same reviewer and conflicts (HTTP 409) for a different reviewer.
- **FR-015**: A reviewer MUST be able to release a claim, returning the submission to
  the unclaimed pool.
- **FR-016**: A reviewer MUST be able to approve a submission with optional notes.
  Approval transitions `pending_review → published`, sets `reviewed_at` and
  `reviewed_by_user_id`, records an audit-chain entry, and publishes
  `marketplace.approved` followed by `marketplace.published` events.
- **FR-017**: A reviewer MUST be able to reject a submission with a required reason.
  Rejection transitions `pending_review → rejected`, sets `reviewed_at` and
  `reviewed_by_user_id`, records an audit-chain entry, publishes a
  `marketplace.rejected` event, and triggers a notification to the submitter that
  carries the rejection reason.

#### Visibility (RLS / row-level security)

- **FR-018**: The default cross-tenant isolation on agent rows MUST hold: a tenant's
  rows are invisible to other tenants by default.
- **FR-019**: A row with `marketplace_scope='public_default_tenant'` AND
  `review_status='published'` MUST be visible to every user of the default tenant.
- **FR-020**: A row with `marketplace_scope='public_default_tenant'` AND
  `review_status='published'` MUST be visible read-only to a user of an Enterprise tenant
  whose `consume_public_marketplace` flag is `true`.
- **FR-021**: A row with `marketplace_scope='public_default_tenant'` AND
  `review_status` other than `published` MUST NOT be visible cross-tenant under any
  circumstance — unapproved drafts MUST never leak.

#### Per-tenant feature flag

- **FR-022**: Super admins MUST be able to set `consume_public_marketplace` to true or
  false on any Enterprise tenant. The flag is meaningless on the default tenant and the
  service MUST refuse attempts to set it there.
- **FR-023**: Each set MUST record a hash-linked audit-chain entry, publish a
  `tenants.feature_flag_changed` Kafka event, and invalidate the tenant resolver cache
  for that tenant.

#### Forking

- **FR-024**: A consumer MUST be able to fork any agent visible to them under the
  visibility rules above into their own workspace or tenant scope. Forking copies
  prompts, capability declarations, tool dependencies, and behaviour metadata; it does
  NOT copy review status, reviewer attribution, or marketing metadata, and it sets
  `forked_from_agent_id`.
- **FR-025**: The fork target scope MUST be `workspace` or `tenant`; a fork MAY NOT
  itself be `public_default_tenant` (forks are private).
- **FR-026**: A successful fork MUST publish a `marketplace.forked` Kafka event and
  record an audit-chain entry on the consumer's tenant.
- **FR-027**: When a public source agent is updated and re-approved, every fork owner
  MUST receive a `marketplace.source_updated` notification stating the source changed
  and the fork has NOT been auto-updated.

### Key Entities

- **AgentProfile (extended)** — gains `marketplace_scope`, `review_status`,
  `reviewed_at`, `reviewed_by_user_id`, `review_notes`, and `forked_from_agent_id`
  fields. The existing `tenant_id`, `workspace_id`, and lifecycle `status` columns are
  unchanged.
- **MarketingMetadata** — embedded in the public-publish request (category, marketing
  description, tags). Only required for `scope=public_default_tenant`.
- **ReviewSubmissionView** — denormalized cross-tenant read model returned by the
  review queue (agent FQN, tenant slug, submitter identity, marketing description,
  submission timestamp, claim state).
- **TenantContext (extended)** — the per-request resolved tenant context gains a
  `consume_public_marketplace` flag read from the tenant's feature_flags JSON.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A default-tenant creator can complete the public-publish flow (open
  publish form → fill marketing metadata → submit) in under 90 seconds on a typical
  desktop browser.
- **SC-002**: A super admin can complete a review (open queue → open submission →
  approve or reject with reason) in under 60 seconds per submission.
- **SC-003**: 100% of attempts to publish public-scope from an Enterprise tenant are
  refused at the UI, the API, and the database. No row with
  `marketplace_scope='public_default_tenant'` and a non-default `tenant_id` may exist
  under any sequence of operations.
- **SC-004**: 100% of cross-tenant visibility tests pass: default-tenant ↔ public-published
  visible; Enterprise-with-flag ↔ public-published visible; Enterprise-without-flag ↔
  public-published invisible; any tenant ↔ public-pending-review invisible.
- **SC-005**: A public-marketplace search query against a representative dataset
  returns the first page in under 1.5 seconds at p95.
- **SC-006**: A fork operation completes in under 5 seconds for a typical agent and
  produces a working copy that the consumer can immediately edit.
- **SC-007**: 95% of public submissions receive a review decision (approve or reject)
  within 5 business days. (Measured against operational SLA, not enforced by code.)

## Assumptions

- The platform has the multi-tenant architecture from UPD-046 in place: every tenant-scoped
  table carries `tenant_id`, RLS enforces tenant isolation by default, the well-known
  default-tenant UUID `00000000-0000-0000-0000-000000000001` is seeded, and a
  platform-staff database role with BYPASSRLS exists for cross-tenant reads.
- Plans, subscriptions, and quotas from UPD-047 are in place: `max_agents_per_workspace`
  exists on the active plan and the fork operation can call into the quota service.
- Public-signup behaviour from UPD-048 is unchanged here: signups land in the default
  tenant and creators on the default tenant are the only set of users eligible to
  publish at public scope.
- The notification surface from UPD-042 (`AlertService.create_admin_alert`) is the
  delivery channel for review-rejection messages and source-updated fan-outs.
- The audit-chain service from UPD-046's hash chain is the source of truth for
  immutable lifecycle history, and every event in this feature gets a corresponding
  hash-linked entry.
- The marketing-category list is platform-curated. Adding or removing categories is a
  code change, not a runtime config change. The default list includes
  `data-extraction`, `summarisation`, `code-assistance`, `research`, `automation`,
  `communication`, `analytics`, `content-generation`, `translation`, `other`.
- Public submission rate limiting uses 5 submissions per rolling 24 hours per submitter
  (the `MARKETPLACE_SUBMISSION_RATE_LIMIT_PER_DAY` setting; can be tuned).
- Public-marketplace deprecation retention defaults to 30 days
  (`MARKETPLACE_DEPRECATION_RETENTION_DAYS`).
- Notifying the source owner on fork is on by default
  (`MARKETPLACE_FORK_NOTIFY_SOURCE_OWNERS=true`).

## Out of Scope

- Monetization, paid public listings, or revenue-share with creators (separate revenue feature).
- Star ratings, reviews, or social signals on public marketplace listings (separate
  marketplace-quality feature).
- Automated reviewer tooling (LLM-as-judge for review decisions): platform staff review
  manually in this feature.
- Cross-tenant marketplace federation between Enterprise tenants. The hub is the default
  tenant and only the default tenant.
- Bulk-publish, bulk-review, or migration tooling. Single-agent flows only in this
  feature.
