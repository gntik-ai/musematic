# Feature Specification: Tags, Labels, and Saved Views

**Feature Branch**: `082-tags-labels-saved-views`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "Add tags (free-form) and labels (key-value) to all major entities. Enable label-based policy expressions. Add saved views (named filter combinations) per user with sharing per workspace."

> **Scoping note (clarifies the brownfield input):** The brownfield input said this feature "modifies all major entity tables." The chosen polymorphic design — `entity_tags` and `entity_labels` as separate join tables keyed on `(entity_type, entity_id)` — explicitly does NOT add columns to the existing major entity tables (`workspaces`, `agents`, `fleets`, `workflows`, `policies`, `certifications`, `evaluation_suites`). This polymorphic shape is the pattern the constitution mandates for tagging (Constitution § Domain-Specific Rules, rule 14: "Every new entity supports tags and labels. Add the polymorphic `entity_tags` / `entity_labels` relations when introducing new entity types; never reinvent tagging per context"). What the existing entity tables DO need is a small additive integration — their list-query endpoints accept tag and label filter parameters. The schema of the entity tables themselves is untouched.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Tag Major Entities and Find Them Across the Platform (Priority: P1)

A workspace member with the right authority MUST be able to attach one or more **tags** (free-form short strings — e.g., `production`, `customer-facing`, `q3-launch`) to any of the major entity types (workspaces, agents, fleets, workflows, policies, certifications, evaluation suites) and later search across the platform for entities carrying a given tag — within the boundaries of what they are allowed to see. This is the substrate every other capability in this feature rests on; without consistent cross-entity tagging, label-based expressions and saved views have nothing to act on.

**Why this priority**: Tagging is the floor. The platform already has many entity types from prior features, and they have grown organically without a uniform organisation surface. Until the tag substrate exists, the platform's catalogue is queryable only by per-entity bespoke filters. P1 is "tag any major entity, find it again across the platform, and never see entities the requester is not authorised to see."

**Independent Test**: Tag one workspace, two agents, one fleet, and one certification with the tag `production`. From the cross-entity tag search, query `tag=production` and confirm exactly those five entities are returned for a requester who can see all of them, that an unauthorised requester sees only the subset they're authorised for, that adding the same tag a second time to the same entity is a no-op (idempotent), and that deleting an entity removes its tag rows automatically.

**Acceptance Scenarios**:

1. **Given** an authenticated workspace member with permission to mutate an agent, **When** they attach the tag `production` to that agent, **Then** the tag is persisted, attributed to the user, and visible on the agent's detail view; re-applying the same tag is a no-op.
2. **Given** five entities of mixed types tagged `production` and an authenticated user authorised to see all of them, **When** the user queries `GET /api/v1/tags/production/entities`, **Then** all five entities are returned grouped by entity type, with no leakage of entities the user cannot see.
3. **Given** a tagged entity, **When** the entity is deleted, **Then** every tag row attached to it is also removed (no dangling tag references).
4. **Given** a workspace member without permission to tag an entity, **When** they attempt to attach a tag, **Then** the action is refused with the platform's standard authorization error and is auditable.
5. **Given** a tag attached by user A on an entity in a workspace that user B can also see, **When** user B views the entity, **Then** the tag is visible to user B; tags are not personal annotations — they are shared organisational metadata within the entity's visibility scope.
6. **Given** an entity with multiple tags, **When** a user removes one tag, **Then** only that tag is removed; the others remain.

---

### User Story 2 - Key-Value Labels with Filtered Listings (Priority: P2)

For richer organisation, an authorised user MUST be able to attach **labels** (key-value pairs — e.g., `env=production`, `tier=critical`, `team=finance-ops`) to any of the major entity types and use those labels to filter the per-entity-type listings (e.g., "list agents where `env=production` AND `tier=critical`"). Labels are key-unique per entity (one value per key per entity); applying a new value to an existing key updates the value. Labels are searchable and filterable; the same RBAC discipline as tags applies — the requester sees only what they are authorised to see.

**Why this priority**: Free-form tags are the floor; labels are the next floor up because they encode structure (a key vocabulary the operator chooses). Per-entity listings (the agent list, the workflow list, the certification list, etc.) become much more useful with `?label.env=production` filtering. P2 is "labels and label filtering are uniformly available across all major entity-type listings."

**Independent Test**: Attach `env=production` and `tier=critical` to two agents, `env=staging` and `tier=critical` to a third, and only `env=production` (no `tier`) to a fourth. Query the agents listing with `?label.env=production&label.tier=critical` and confirm exactly the first two are returned. Update the value of `env` on the third agent to `production`; re-query and confirm three are returned. Delete `tier` from one of the original two; re-query and confirm two remain.

**Acceptance Scenarios**:

1. **Given** an authorised user, **When** they attach `env=production` to an agent, **Then** the label is persisted with that key/value, attributed to the user, and visible on the agent detail view.
2. **Given** an entity already carrying `env=staging`, **When** an authorised user re-attaches `env=production`, **Then** the label is updated in place (one value per key per entity); the previous value is recorded in the audit trail (FR-CC-2).
3. **Given** a per-entity-type listing endpoint (e.g., agents), **When** a user queries with `?label.env=production&label.tier=critical`, **Then** only entities carrying both labels with those exact values (within the user's visibility) are returned.
4. **Given** a label attached to an entity, **When** an authorised user removes the label, **Then** only that key is removed from that entity; other labels remain.
5. **Given** a label attached by user A, **When** user B (with permission to mutate the same entity) updates the label's value, **Then** the update succeeds and is attributed to user B; labels are organisational metadata, not personal annotations.
6. **Given** an attempt to attach a label whose key matches a platform-reserved namespace (e.g., `system.*`), **When** a non-superadmin attempts the operation, **Then** the operation is refused with a clear error pointing at the reserved-prefix policy.

---

### User Story 3 - Label-Based Expressions in Policy Rules (Priority: P3)

The platform's existing policy engine MUST be able to evaluate **label expressions** as part of policy authoring — for example, a policy that applies only when the target carries `env=production AND tier=critical`, or only when the target does NOT carry `lifecycle=experimental`. The expression language MUST be small, predictable, and machine-checkable; expressions that reference labels the operator could never produce should be flagged at policy authoring time, not silently fail to match at runtime.

**Why this priority**: Label-based policy expressions are how labels graduate from "descriptive metadata" to "machine-actionable governance." The existing policy engine already evaluates conditions (purpose, role, FQN visibility, budget) — adding a label-condition operator is a small, focused extension. P3 is "an authorised policy author can express `apply this policy when target labels match X` and the expression evaluates correctly at the gateway."

**Independent Test**: Author a policy that applies "to agents whose labels include `env=production`." Verify that an agent with `env=production` is governed by the policy at the tool gateway; an agent with `env=staging` is not; an agent with no `env` label is not. Author a second policy with the conjunction `env=production AND tier=critical`; verify the conjunction is enforced. Attempt to author a policy with a malformed expression (e.g., dangling parenthesis) and confirm the validator refuses at authoring time with a clear error.

**Acceptance Scenarios**:

1. **Given** a policy whose match-condition is the label expression `env=production`, **When** the gateway evaluates a tool call from an agent carrying `env=production`, **Then** the policy applies to that call.
2. **Given** the same policy, **When** the gateway evaluates a tool call from an agent carrying `env=staging` or carrying no `env` label at all, **Then** the policy does NOT apply.
3. **Given** a policy with the expression `env=production AND tier=critical`, **When** the gateway evaluates a target carrying both labels with those values, **Then** the policy applies; if either is missing or different, the policy does not apply.
4. **Given** a policy with a malformed expression, **When** an authorised user attempts to save the policy, **Then** the platform refuses the save with a validator error pointing at the location of the syntax problem; the policy is NOT persisted in a half-broken state.
5. **Given** a policy whose expression references a label key that is actively in use, **When** the policy evaluates, **Then** evaluation completes within the policy gateway's existing latency budget — the label substrate must not slow down the hot path.
6. **Given** a policy whose expression uses negation (e.g., `NOT lifecycle=experimental`), **When** the gateway evaluates a target with no `lifecycle` label, **Then** the negation behaves consistently with the documented semantics of "missing key" (defined precisely in the language documentation — never ambiguous).

---

### User Story 4 - Saved Views Per User with Workspace Sharing (Priority: P4)

A user MUST be able to save a frequently-used filter combination (entity type + tag/label/standard-filter combination + display preferences) as a named **saved view** — for example, "Production agents in finance-ops with active certifications." Saved views are personal by default; a user MAY mark a view as **shared** with their current workspace, in which case other workspace members see it in their saved-view list. Saved views are the productivity surface that turns the substrate of US1–US3 into something operators reach for daily, and are the building block FR-576 (Admin Data Table Standards) explicitly relies on.

**Why this priority**: Once tags, labels, and per-entity-type listings exist, the next bottleneck is "I have to reconstruct my filters every time I open this page." Saved views address that by making the operator's working set first-class. P4 is "a user can save a filter, name it, find it again on next visit, and optionally share it with their workspace."

**Independent Test**: As user A in workspace X, save a view "Prod agents" filtering the agents listing by `label.env=production`. Confirm the view appears in user A's saved-view list. As user B in the same workspace X, confirm "Prod agents" does NOT appear (it is personal). User A marks the view as shared; user B re-loads and now sees "Prod agents" in their list. User A renames the view; user B sees the rename. User A leaves workspace X; the shared view remains visible to user B (the view was shared with the workspace, not transferred). User A deletes the view from a workspace they no longer belong to → the platform handles this gracefully per the documented rule.

**Acceptance Scenarios**:

1. **Given** an authenticated user on a per-entity-type listing with active filters, **When** they save the view with a name, **Then** the view is persisted attributed to them, scoped to the entity type, and immediately appears in their saved-view list.
2. **Given** a saved view marked as personal (the default), **When** another workspace member queries their own saved views, **Then** the view does NOT appear in the other member's list.
3. **Given** a saved view, **When** the owner toggles it to shared, **Then** every other member of the same workspace sees the view in their list within the platform's stated p95 propagation latency; toggling back to personal removes it from other members' lists.
4. **Given** a shared saved view, **When** any member of the workspace applies the view, **Then** the same filter combination is applied to their listing — a deterministic, reproducible result.
5. **Given** a saved view referencing a label key or value that no longer exists in the workspace, **When** the view is applied, **Then** the listing returns an empty (or appropriately reduced) result set with a clear "this filter matches nothing" indicator rather than a stack trace or silent fallback.
6. **Given** a saved view whose owner has left the workspace, **When** another workspace member views the saved-view list, **Then** the platform handles the orphaned-owner case per a documented rule — either keep the shared view with attribution to a "former member" notice, or transfer ownership to a workspace admin; never silently delete or silently break.
7. **Given** a saved view, **When** the owner deletes it, **Then** it is removed from every member's list (whether shared or personal); deletion is auditable.

---

### Edge Cases

- **Tag normalisation**: Whether tags are case-sensitive (`Production` vs `production`) and how whitespace is handled MUST be specified once and applied uniformly. Inconsistent casing across the platform makes the cross-entity search useless.
- **Reserved label-key namespaces**: Some keys (e.g., `system.*`, `platform.*`) MUST be reserved for platform-managed labels and refused to non-superadmin actors. Reservation MUST be enforced server-side.
- **Maximum tag count per entity**: A documented per-entity limit (e.g., 50 tags) prevents abuse and keeps query plans bounded. Exceeding the limit returns a clear 422 rather than silently degrading.
- **Maximum labels per entity** and **maximum value length** (the input proposed VARCHAR(512)): same as above — bounded, documented, enforced.
- **Tagging an entity the requester cannot mutate**: refused with the platform's standard authorisation error, audited, surfaced cleanly to the UI.
- **Cross-entity tag search across visibility boundaries**: results MUST be filtered at the SQL layer (NOT in the response serializer) so unauthorised entity rows never reach the requester (defence in depth + spec FR-CC-1).
- **Bulk tag application**: applying the same tag to many entities at once MUST be either atomic per-batch or clearly partial-with-feedback (each entity result reported); silent partial success is unacceptable.
- **Label value type coercion**: All label values are strings in v1. If a user attempts to use `=` with a numeric-shaped value, the comparison is string equality, not numeric. Documented loudly to prevent surprise.
- **Label-expression performance on hot path**: the policy gateway evaluates expressions per tool call; expressions referencing labels MUST resolve via an index hit (not a sequential scan) and MUST cache compiled expression ASTs.
- **Saved-view referencing a deleted entity type**: the view declares an `entity_type`; if that type is removed from the platform, applying the view returns the documented empty/error path, not a silent crash.
- **Shared saved view authored by a former workspace member**: covered above — needs a documented orphan-owner rule.
- **Saved view filter shape evolution**: when the listing's filter schema evolves (e.g., a new filter parameter is added), older saved views MUST continue to apply correctly; backwards-incompatible filter changes require a migration of stored views, not a silent break.
- **Tag/label drift across replication boundaries**: in multi-region deployments (feature 081), tags and labels replicate via the same path as the parent entity; an entity's tags reaching the secondary on the same RPO as the entity itself is the contract.
- **Audit on every mutation**: every tag/label/saved-view create/update/delete is auditable per constitution rule 14 and FR-CC-2.
- **System-managed labels written by other features**: feature 080 (`incident_response/`), feature 079 (`cost_governance/`), and feature 081 (`multi_region_ops/`) may want to attach platform-managed labels (e.g., `platform.region=eu-west`); these writes MUST go through the same service interface but with a service-account caller and the reserved namespace privilege.
- **Cascade on entity deletion**: every `entity_tags` and `entity_labels` row attached to a deleted entity MUST be removed by the same transaction that deletes the entity (FK with `ON DELETE CASCADE` or equivalent application-level guarantee). Orphaned tag/label rows MUST NOT exist.
- **Saved view applied by a user who lost permission to see one of the underlying filtered entity types**: the listing returns the empty-or-reduced set per the standard RBAC discipline, not a hard error.

## Requirements *(mandatory)*

### Functional Requirements

**Tags (FR-511 — tags portion)**

- **FR-511.1**: System MUST support attaching free-form tags (short strings) to any of the major entity types: workspaces, agents, fleets, workflows, policies, certifications, evaluation suites.
- **FR-511.2**: Tag attachment MUST be idempotent on `(entity_type, entity_id, tag)`; re-applying the same tag is a no-op (no duplicate row, no error).
- **FR-511.3**: System MUST attribute each tag attachment to the user who created it and timestamp it.
- **FR-511.4**: System MUST support cross-entity tag search — given a tag, return the set of entities of any of the major types carrying that tag, grouped by entity type, filtered by the requester's visibility (RBAC at the SQL layer per FR-CC-1).
- **FR-511.5**: When an entity is deleted, every tag attached to it MUST be removed in the same operation; no dangling tag rows.
- **FR-511.6**: Tag normalisation rules (case-sensitivity, whitespace handling, allowed character set, length limits) MUST be specified, enforced server-side, and applied uniformly.
- **FR-511.7**: System MUST enforce a documented per-entity tag-count maximum and reject excess attachments with a clear error.
- **FR-511.8**: Tag mutation actions (attach, detach) MUST be governed by the platform's existing per-entity write authority — a user who cannot mutate the entity cannot tag it.

**Labels (FR-511 — labels portion)**

- **FR-511.9**: System MUST support attaching key-value labels to the same set of major entity types.
- **FR-511.10**: Labels MUST be unique per `(entity_type, entity_id, label_key)`; re-attaching with a different value updates the value in place; the previous value MUST be captured by the audit trail.
- **FR-511.11**: System MUST attribute label create/update/delete to the actor and timestamp it.
- **FR-511.12**: Per-entity-type listing endpoints (agents, workflows, etc.) MUST accept label filter parameters (e.g., `?label.env=production`) and return only entities matching all specified key=value conjunctions, within the requester's visibility.
- **FR-511.13**: System MUST reserve a documented set of label-key namespaces (e.g., `system.*`, `platform.*`) for platform-managed labels; only superadmin or service-account actors may write to reserved namespaces.
- **FR-511.14**: Label keys and values MUST have documented maximum lengths and allowed character sets, enforced server-side.
- **FR-511.15**: When an entity is deleted, every label attached to it MUST be removed in the same operation.

**Label-Based Policy Expressions (FR-511 — policy hook)**

- **FR-511.16**: The platform's existing policy engine MUST be extended to evaluate label expressions over a target entity's labels as part of a policy's match condition.
- **FR-511.17**: The expression language MUST support at minimum: `key=value` equality, `key!=value` inequality, conjunction (`AND`), disjunction (`OR`), negation (`NOT`), grouping with parentheses, and presence/absence checks (`HAS key`, `NOT HAS key`).
- **FR-511.18**: Expression syntax MUST be validated at policy authoring time; malformed expressions MUST be refused at save with a clear pointer to the location of the error — half-broken policies are unacceptable.
- **FR-511.19**: Expression evaluation MUST not regress the policy gateway's existing per-call latency budget; expression ASTs MUST be compiled once at policy load and cached, with label lookups served from index hits.
- **FR-511.20**: The semantics of "label key is missing" under negation and inequality MUST be specified precisely in the language documentation and applied uniformly — never ambiguous.

**Saved Views (FR-512)**

- **FR-512.1**: Authenticated users MUST be able to save a named filter combination (entity type, filter parameters, display preferences) as a saved view scoped to themselves.
- **FR-512.2**: Saved views are personal by default; a user MAY toggle a view to shared with their current workspace, in which case it appears in every workspace member's saved-view list.
- **FR-512.3**: Toggling a view's shared state MUST propagate to other members within the platform's stated p95 latency for view-list freshness.
- **FR-512.4**: Saved views MUST capture exactly the filter parameters and display preferences supported by the underlying listing endpoint; the view MUST be reproducible — any member applying the view MUST see the same filter shape.
- **FR-512.5**: When a saved view's owner leaves the workspace it was shared into, the platform MUST handle the orphan case per a documented rule (preserve with a "former member" attribution OR transfer to a workspace admin OR documented alternative); silent deletion or silent breakage is unacceptable.
- **FR-512.6**: When a saved view references a label key/value or tag that no longer exists in the workspace, applying the view MUST return the listing's standard empty-result presentation rather than a stack trace.
- **FR-512.7**: Saved view CRUD operations MUST be auditable per FR-CC-2.
- **FR-512.8**: Saved views MUST integrate with the admin data-table standards (FR-576) so admin list pages get the saved-view affordance uniformly.

**Cross-Cutting**

- **FR-CC-1**: Tag, label, and saved-view operations MUST be governed by the platform's existing RBAC and visibility rules; cross-entity tag search MUST filter at the SQL layer (not the response serializer) so unauthorised rows never reach the requester (constitution Principle IX, rule 18).
- **FR-CC-2**: Every tag, label, and saved-view mutation (attach, detach, update, share, unshare, delete) MUST emit an audit chain entry through the platform's existing audit-chain service — never written directly (constitution rule 9, 32).
- **FR-CC-3**: System MUST integrate with the platform's existing notifications subsystem (feature 077) for any user-targeted notifications related to shared views (e.g., "user X shared view Y with your workspace") — never introduce a parallel notification path.
- **FR-CC-4**: Tags, labels, and saved views MUST survive workspace archival; historical record is durable.
- **FR-CC-5**: All operator-facing surfaces (the tag search, the per-entity-type listing's label filter UI, the saved-view picker) MUST be reachable from the existing application shell and the existing entity-detail / entity-listing pages — no new application is created (constitution rule 45 + 47).
- **FR-CC-6**: The constitutionally-declared REST prefixes `/api/v1/tags/*`, `/api/v1/labels/*`, and `/api/v1/saved-views/*` (constitution § REST Prefix Registry lines 808–810) MUST be the home for the new endpoints; admin-only authoring of platform-reserved labels lives under the segregated `/api/v1/admin/*` prefix per rule 29.
- **FR-CC-7**: Workspace-scoped resource boundaries MUST be enforced (constitution rule 47): a saved view shared with workspace X is visible only to workspace X members; an entity tagged in workspace X is searchable only by users with visibility into workspace X's entities.
- **FR-CC-8**: System-managed label writes (e.g., from features 077, 079, 080, 081) MUST go through the same label service interface but with a service-account caller and reserved-namespace privilege; no parallel write paths.

### Key Entities

- **Entity Tag**: A polymorphic join row carrying `(entity_type, entity_id, tag, created_by, created_at)`. Free-form short string tag attached to any major entity. Idempotent on `(entity_type, entity_id, tag)`. Cascades on entity deletion.
- **Entity Label**: A polymorphic join row carrying `(entity_type, entity_id, label_key, label_value, created_by, created_at, updated_at)`. Key-unique per entity (one value per key per entity). Re-attachment updates the value with audit. Cascades on entity deletion.
- **Saved View**: A named filter combination owned by a user, optionally shared with a workspace. Carries `entity_type`, `filters` (JSONB matching the underlying listing's filter contract), `shared` boolean, ownership, and timestamps. Reproducible — any authorised viewer applying the view sees the same filter shape.
- **Reserved Namespace Policy**: The documented set of label-key namespaces reserved for platform-managed writes (e.g., `system.*`, `platform.*`). Configuration concern, not a stored entity in this spec — but the rule MUST be expressible and machine-enforced.
- **Label Expression**: A small, validated DSL string (`env=production AND tier=critical`) attached to policy match conditions. Compiled once to an AST and cached at policy load.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tags can be attached to and detached from every one of the seven major entity types (workspaces, agents, fleets, workflows, policies, certifications, evaluation suites) — verified by automated assertion across all seven types.
- **SC-002**: A cross-entity tag search returns every entity carrying the tag that the requester is authorised to see, and ZERO entities outside that authorisation scope — verified by automated authorisation tests across all major entity types.
- **SC-003**: When an entity is deleted, every `entity_tags` and `entity_labels` row attached to it is removed in the same transaction — verified by automated assertion (no orphan rows).
- **SC-004**: Per-entity-type listings accept label filters (e.g., `?label.env=production`) on every one of the seven major entity types and return correctly filtered results within the listing's stated p95 latency budget — verified by automated assertion across all seven types.
- **SC-005**: Re-attaching a label key with a different value updates the value in place; exactly one row per `(entity_type, entity_id, label_key)` exists at all times — verified by automated assertion.
- **SC-006**: Reserved label-key namespaces (e.g., `system.*`) refuse non-superadmin writes with a 403 carrying a clear error — verified by automated assertion.
- **SC-007**: Label-based policy expressions evaluate correctly across the documented operator set (`=`, `!=`, `AND`, `OR`, `NOT`, `HAS`, parens) — verified by a property-based test of the expression evaluator.
- **SC-008**: Malformed label expressions are refused at policy save with a syntax error pointing at the failing token; no half-broken policies persist — verified by negative-test coverage of the parser.
- **SC-009**: Policy gateway p95 latency does not regress when label expressions are introduced; expressions resolve via index hits — verified by a load test comparing pre/post-feature gateway latency under the same workload.
- **SC-010**: Saved views are personal by default; toggling shared makes the view visible to other workspace members within the platform's stated p95 propagation latency; toggling back removes it — verified by automated assertion.
- **SC-011**: Saved views referencing labels/tags that no longer exist return the standard empty-result presentation, never a stack trace — verified by automated assertion.
- **SC-012**: Orphan-owner saved views (owner left the workspace they shared into) are handled per the documented rule and never silently deleted or broken — verified by automated assertion.
- **SC-013**: Every tag, label, and saved-view mutation emits an audit-chain entry — verified by automated audit-coverage check across the mutation surface.
- **SC-014**: No unauthorised entity row leaks through the cross-entity tag search, the label-filtered listings, the policy-target evaluation, or the saved-view application — verified by automated authorisation tests across all four read paths.

## Assumptions

- The platform's existing major entity tables are stable enough to be treated as a closed set for v1: workspaces, agents, fleets, workflows, policies, certifications, evaluation suites. Adding additional entity types to the polymorphic substrate is a future-additive change; the substrate's design supports it without schema migration.
- The platform's existing audit chain (UPD-024), notifications (feature 077), and RBAC subsystems are reused; this feature does not introduce a parallel audit, notification, or authorisation path.
- The platform's existing application shell is the home for the saved-view picker and label filter UI on per-entity-type listings; no new application is created.
- The platform's existing policy engine (feature 028) is extended with one new evaluator (label expression); the policy authoring UI is extended to accept the expression text. The expression language is small and machine-checkable; no LLM is involved in evaluation (constitution rule 50 N/A — labels do not require previews).
- The platform's existing residency rules apply unchanged; tags and labels replicate via the parent entity's existing replication path (feature 081).
- The set of label-key reserved namespaces (`system.*`, `platform.*`) is fixed at v1; further reserved namespaces are an additive change.
- Tag and label values are strings in v1; numeric/typed values are out of scope. Comparisons are string equality.
- Multi-currency / locale-specific tag normalisation is out of scope for v1; the platform-default locale's case-folding rules apply.
- The seven major entity types listed in the planning input are the v1 set; adding new entity types to the substrate is a future-additive change governed by constitution rule 14.

## Out of Scope (v1)

- Numeric/typed label values; v1 stores strings only and compares by string equality.
- Hierarchical tags or tag taxonomies (e.g., "tag tree" with parent/child relationships).
- Suggested-tag autocomplete based on usage patterns or LLM-assisted recommendations.
- Cross-workspace tag sharing or "global" tags above the workspace boundary.
- Bulk tag/label import from external systems (e.g., a CSV importer); v1 is API-driven only.
- Saved-view scheduling (e.g., "email me this view weekly"); the saved-view substrate enables future scheduling features but the scheduler itself is not in v1.
- Saved-view export as a portable artifact between deployments; v1 is intra-deployment.
- Per-tag or per-label permissions beyond what the parent entity already enforces (e.g., "only HR can read the `compliance` tag"); v1 inherits the parent entity's RBAC.
- Tag/label-driven dashboards or analytics rollups (e.g., "cost by label.team"); the substrate makes this possible but the dashboards are a separate feature.

## Dependencies and Brownfield Touchpoints

This feature is additive to the existing platform. The relevant existing capabilities the new common module relies on or extends:

- **Constitution rule 14** (`Domain-Specific Rules`, audit pass): explicitly mandates the polymorphic `entity_tags` / `entity_labels` substrate this feature builds. The feature is the canonical implementation of that rule.
- **Constitution § REST Prefix Registry lines 808–810**: `/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*` are already declared. This feature implements those prefixes; admin-only authoring of platform-reserved labels uses the segregated `/api/v1/admin/*` prefix per rule 29.
- **Audit chain** (`security_compliance/services/audit_chain_service.py`): canonical write path for every tag, label, and saved-view mutation (rule 9, 32, FR-CC-2).
- **Existing major entity bounded contexts** — `workspaces/`, `registry/` (agents), `fleets/`, `workflows/`, `policies/`, `trust/` (certifications), `evaluation/` (evaluation suites): each has a per-entity-type listing endpoint that this feature extends additively to accept the new tag and label filter parameters; no rewrite of those listings.
- **Policy engine** (feature 028, `policies/`): extended with one new label-expression evaluator. The existing policy authoring UI is extended to accept expression text. The hot-path evaluation goes through the existing policy gateway with no latency regression (FR-511.19, SC-009).
- **Registry query service** (`registry/services/registry_query_service.py` per the planning input): extended additively to accept `?tags=…` and `?label.key=value` filter parameters.
- **Notifications** (feature 077): user-targeted notifications about shared-view events (e.g., "your colleague shared a view with your workspace") flow through the existing notifications subsystem.
- **Multi-region replication** (feature 081): tag and label rows replicate via the parent entity's existing replication path; no new replication target.
- **Admin data-table standards** (FR-576): saved views are explicitly the building block FR-576 relies on for its "saved views per user" affordance.
- **Operator dashboard / application shell**: the saved-view picker and label filter UI integrate into the existing application shell rather than a new surface (rule 45, 47, FR-CC-5).
- **Existing user / workspace identity surfaces**: tag/label/saved-view ownership and workspace scoping derive from the existing user identity and workspace membership models.

The implementation strategy (specific tables, services, schemas, expression-language grammar, code-level integration points across the seven entity-type bounded contexts) is intentionally deferred to the planning phase. The brownfield input that motivated this spec is preserved in the feature folder as `planning-input.md`.
