# Tasks: Tags, Labels, and Saved Views

**Feature**: 082-tags-labels-saved-views
**Branch**: `082-tags-labels-saved-views`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Planning Input**: [planning-input.md](./planning-input.md)

User stories (from spec.md):
- **US1 (P1)** — Tag major entities + cross-entity tag search (the substrate floor; rule 14 canonical implementation)
- **US2 (P2)** — Key-value labels + filtered listings across all 7 entity types
- **US3 (P3)** — Label-based policy expressions (DSL + AST + Redis-cached compilation + governance hook with NO gateway latency regression)
- **US4 (P4)** — Saved views per user with workspace sharing (the productivity surface FR-576 relies on)

Each user story is independently testable per spec.md.

---

## Phase 1: Setup

- [X] T001 Create new shared-substrate directory `apps/control-plane/src/platform/common/tagging/` with subdirs `label_expression/`; add empty `__init__.py` to each; this is `common/`-shared, NOT a new BC (declared variance from rules 24/25 — see plan's Constitution Check)
- [X] T002 [P] Add canonical constants to `apps/control-plane/src/platform/common/tagging/constants.py`: `ENTITY_TYPES = ("workspace","agent","fleet","workflow","policy","certification","evaluation_run")` (note: the seventh is `evaluation_run` matching `evaluation/models.py:175 EvaluationRun`, NOT `evaluation_suite` as the planning input said — correction documented in plan); `RESERVED_LABEL_PREFIXES = ("system.","platform.")`; `MAX_TAGS_PER_ENTITY = 50`; `MAX_LABELS_PER_ENTITY = 50`; `MAX_TAG_LEN = 128`; `MAX_LABEL_KEY_LEN = 128`; `MAX_LABEL_VALUE_LEN = 512`; `TAG_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")` (case-sensitive, ASCII-printable + hyphen + underscore + period); `LABEL_KEY_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]*$")` (must start with letter to keep namespacing readable); `REDIS_KEY_AST_TEMPLATE = "tags:label_expression_ast:{policy_id}:{version}"`; `REDIS_KEY_AST_TTL_SECONDS = 86400`
- [X] T003 [P] Add `TaggingSettings` extension to `apps/control-plane/src/platform/common/config.py`: `tagging_label_expression_lru_size` (int, default 256 — in-process LRU on top of Redis for the gateway hot path), `tagging_label_expression_redis_ttl_seconds` (int, default 86400), `tagging_cross_entity_search_max_visible_ids` (int, default 10000 — bounded WHERE clause to prevent unbounded query plans), `tagging_saved_view_share_propagation_target_seconds` (int, default 5 — the propagation budget for SC-010), `tagging_orphan_owner_resolution` (str, default `"transfer_to_workspace_superadmin"` — the documented orphan-owner rule per FR-512.5; alternative values explicitly out of scope for v1)
- [X] T004 [P] Add the **entity-type discriminator helper** to `apps/control-plane/src/platform/common/tagging/entity_types.py`: `get_entity_type_string(model: type[Base]) -> str` mapping the seven SQLAlchemy classes to their `ENTITY_TYPES` strings (`Workspace` → `"workspace"`, `AgentProfile` → `"agent"`, `Fleet` → `"fleet"`, `WorkflowDefinition` → `"workflow"`, `PolicyPolicy` → `"policy"`, `TrustCertification` → `"certification"`, `EvaluationRun` → `"evaluation_run"`); the inverse `get_entity_class(entity_type: str) -> type[Base]` for the visibility resolver

---

## Phase 2: Foundational (blocks every user story)

- [X] T005 Create Alembic migration `apps/control-plane/migrations/versions/065_tags_labels_saved_views.py` (rebase to current head at merge time): creates **`entity_tags`** (`id` UUID PK, `entity_type` VARCHAR(32) CHECK against `ENTITY_TYPES`, `entity_id` UUID NOT NULL, `tag` VARCHAR(128) NOT NULL CHECK regex `^[a-zA-Z0-9._-]+$`, `created_by` UUID FK to `users.id`, `created_at` TIMESTAMPTZ default now; **UNIQUE on `(entity_type, entity_id, tag)`** for idempotency per FR-511.2; index `idx_entity_tags_type_id` on `(entity_type, entity_id)` for the per-entity tag list; index `idx_entity_tags_tag` on `(tag)` for the cross-entity search hot path); creates **`entity_labels`** (`id` UUID PK, `entity_type` VARCHAR(32) CHECK against `ENTITY_TYPES`, `entity_id` UUID NOT NULL, `label_key` VARCHAR(128) NOT NULL CHECK regex `^[a-zA-Z][a-zA-Z0-9._-]*$`, `label_value` VARCHAR(512) NOT NULL, `created_by` UUID FK to `users.id`, `created_at` TIMESTAMPTZ, `updated_at` TIMESTAMPTZ; **UNIQUE on `(entity_type, entity_id, label_key)`** for FR-511.10's "one value per key per entity"; index `idx_entity_labels_type_id` on `(entity_type, entity_id)`; index `idx_entity_labels_kv` on `(label_key, label_value)` for the filter-listings hot path; index `idx_entity_labels_key` on `(label_key)` for label-key autocomplete in the UI); creates **`saved_views`** (`id` UUID PK, `owner_id` UUID NOT NULL FK to `users.id`, `workspace_id` UUID FK to `workspaces.id` (nullable for personal views that aren't workspace-scoped — but in practice every view declares its workspace at create time so the field is rarely NULL), `name` VARCHAR(256) NOT NULL, `entity_type` VARCHAR(32) CHECK against `ENTITY_TYPES`, `filters` JSONB NOT NULL (matches the underlying listing's filter contract; validated server-side at create), `shared` BOOLEAN default false, `version` INT default 1 (optimistic concurrency for renames), `created_at` TIMESTAMPTZ, `updated_at` TIMESTAMPTZ; index `(owner_id, entity_type)` for the user's-saved-views query; partial index `(workspace_id, entity_type) WHERE shared=true` for the shared-views query; UNIQUE on `(owner_id, workspace_id, name)` so a user can't have two views with the same name in the same workspace). **No FK with ON DELETE CASCADE** is added on `entity_tags.entity_id` / `entity_labels.entity_id` — the polymorphic shape forbids it; cascade is application-layer per the plan's complexity tracking; this is verified by SC-003 in T024
- [X] T006 [P] Add SQLAlchemy models to `apps/control-plane/src/platform/common/tagging/models.py`: `EntityTag`, `EntityLabel`, `SavedView`. **No SQLAlchemy `relationship()` mappings** to the seven entity classes (the polymorphic `(entity_type, entity_id)` shape cannot be a typed `relationship()`); `entity_id` is a plain UUID column. `SavedView.owner_id` and `SavedView.workspace_id` are typed FKs (referencing `users.id` and `workspaces.id` — these ARE typed relationships; only the polymorphic ones aren't)
- [X] T007 [P] Add Pydantic schemas to `apps/control-plane/src/platform/common/tagging/schemas.py`: `TagAttachRequest` (`tag: str`), `TagDetachRequest` (`tag: str`), `TagResponse` (`tag`, `created_by`, `created_at`), `EntityTagsResponse` (list per entity), `LabelAttachRequest` (`key: str`, `value: str`), `LabelResponse` (`key`, `value`, `created_by`, `created_at`, `updated_at`, `is_reserved` boolean computed at read time), `EntityLabelsResponse`, `LabelFilterParams` (parsed from `?label.env=production&label.tier=critical`; values are AND-conjunctive per FR-511.12), `CrossEntityTagSearchRequest` (`tag: str`, optional `entity_types: list[str]` filter, cursor pagination), `CrossEntityTagSearchResponse` (entities grouped by `entity_type`, with the requester's RBAC scope already applied at the SQL layer), `SavedViewCreateRequest`, `SavedViewUpdateRequest`, `SavedViewResponse` (carries `is_owner`, `is_shared`, `is_orphan_transferred` flags so the UI can render the "former member" attribution per FR-512.5), `SavedViewShareToggleRequest` (`shared: bool`), `LabelExpressionValidationRequest` (`expression: str`), `LabelExpressionValidationResponse` (`valid: bool`, `error: {line, col, token, message} | None`)
- [X] T008 [P] Add domain exceptions to `apps/control-plane/src/platform/common/tagging/exceptions.py`: `TagAttachLimitExceededError` → 422 (per-entity ceiling per FR-511.7); `LabelAttachLimitExceededError` → 422; `InvalidTagError` → 422 (pattern violation per FR-511.6); `InvalidLabelKeyError` → 422 (pattern violation); `LabelValueTooLongError` → 422; `ReservedLabelNamespaceError` → 403 (non-superadmin write to `system.*` / `platform.*` per FR-511.13); `SavedViewNotFoundError` → 404; `SavedViewNameTakenError` → 409 (UNIQUE violation on `(owner_id, workspace_id, name)`); `LabelExpressionSyntaxError` → 422 (carries `line`, `col`, `token`, `message` for FR-511.18); `EntityTypeNotRegisteredError` → 422 (raised when an entity_type string is not in `ENTITY_TYPES`); `EntityNotFoundForTagError` → 404 (raised when attaching a tag to a non-existent entity)
- [X] T009 [P] Add events to `apps/control-plane/src/platform/common/tagging/events.py`: payload classes `EntityTagAttachedPayload`, `EntityTagDetachedPayload`, `EntityLabelUpsertedPayload` (carries old + new value for the audit trail per FR-511.10), `EntityLabelDetachedPayload`, `SavedViewSharedPayload`, `SavedViewUnsharedPayload`, `SavedViewDeletedPayload`; event types are namespaced as `tagging.tag.attached`, `tagging.tag.detached`, `tagging.label.upserted`, `tagging.label.detached`, `tagging.saved_view.shared`, `tagging.saved_view.unshared`, `tagging.saved_view.deleted` on a new topic `common_tagging.events`. (This topic is NOT in the constitutional registry — adding it requires a constitution amendment OR using the existing `audit.events` channel. **Decision**: route through the existing audit-chain emission only; the audit chain entries ARE the durable log. Skip a separate Kafka topic for v1 — keeps the dependency surface clean. Re-evaluate if downstream consumers need it.)
- [X] T010 Create `apps/control-plane/src/platform/common/tagging/repository.py`: `insert_tag(entity_type, entity_id, tag, created_by)` with `INSERT … ON CONFLICT (entity_type, entity_id, tag) DO NOTHING RETURNING *` for idempotency per FR-511.2; `delete_tag(entity_type, entity_id, tag)`; `list_tags_for_entity(entity_type, entity_id) -> list[EntityTag]`; `list_entities_by_tag(tag, visible_entity_ids_by_type: dict[str, set[UUID]], cursor, limit) -> list[(entity_type, entity_id)]` (RBAC enforced at the SQL `WHERE entity_type=? AND entity_id IN (...)` per FR-CC-1 — never post-filter); `count_tags_for_entity(entity_type, entity_id)` for the per-entity ceiling check; `upsert_label(entity_type, entity_id, key, value, updated_by)` (INSERT or UPDATE-on-conflict-return-old-value so the audit trail captures the previous value per FR-511.10); `delete_label(entity_type, entity_id, key)`; `list_labels_for_entity(entity_type, entity_id)`; `filter_entities_by_labels(entity_type, label_filters: dict[str,str], visible_entity_ids: set[UUID], cursor, limit) -> list[UUID]` (the JOIN against `entity_labels` with conjunctive AND of `(label_key=? AND label_value=?)` clauses; index-served per the perf goal); `count_labels_for_entity(entity_type, entity_id)`; `cascade_on_entity_deletion(entity_type, entity_id)` (deletes both tag rows AND label rows in one call — invoked from each entity BC's delete path inside the same SQLAlchemy transaction per the plan's cascade contract); saved-view CRUD: `insert_saved_view`, `get_saved_view`, `list_personal_views(owner_id, entity_type)`, `list_shared_views(workspace_id, entity_type)`, `update_saved_view(id, expected_version, ...)` with optimistic concurrency, `delete_saved_view(id)`, `transfer_saved_view_ownership(id, new_owner_id)` (the orphan-owner resolution per FR-512.5), `list_views_owned_by_user_in_workspace(owner_id, workspace_id)` (used at orphan-owner resolution time)
- [X] T011 [P] Create `apps/control-plane/src/platform/common/tagging/visibility_resolver.py`: `async def resolve_visible_entity_ids(requester: User, entity_types: list[str] | None = None) -> dict[str, set[UUID]]` calls each entity BC's "list visible to user" service interface (e.g., `WorkspaceService.list_visible_for(requester)`, `RegistryService.list_visible_agents(requester)`, etc.) to build the per-entity-type visible-id set; bounded by `tagging_cross_entity_search_max_visible_ids` (excess returns a 422 with a clear "narrow your search" hint — prevents unbounded WHERE clauses); the helper is the boundary that honours Principle IV (no cross-BC table access — every visibility check goes through the owning BC's public service interface) and FR-CC-1 (RBAC at the SQL layer). For v1, the seven entity BCs each expose a `list_visible_<entity>(requester) -> set[UUID]` method; this resolver is the single caller across the seven
- [X] T012 [P] Create `apps/control-plane/src/platform/common/tagging/filter_extension.py`: `parse_tag_label_filters(request: Request) -> TagLabelFilterParams` extracts `?tags=a,b,c` (comma-separated; AND-conjunctive — entity must carry ALL specified tags) and `?label.env=production&label.tier=critical` (any param starting with `label.` is treated as a label filter; AND-conjunctive); returns a small dataclass each entity BC's existing handler consumes; the helper centralises the *parsing* without centralising the *query semantics* per the plan's complexity tracking
- [X] T013 Create the three sub-services and the facade:
  - `apps/control-plane/src/platform/common/tagging/tag_service.py` `TagService`: stub with method signatures (`attach`, `detach`, `list_for_entity`, `cross_entity_search`, `cascade_on_entity_deletion`); implementations land in US1 phase
  - `apps/control-plane/src/platform/common/tagging/label_service.py` `LabelService`: stub (`attach`, `detach`, `list_for_entity`, `filter_query`, `cascade_on_entity_deletion`, `validate_reserved_namespace`); implementations land in US2 phase
  - `apps/control-plane/src/platform/common/tagging/saved_view_service.py` `SavedViewService`: stub (`create`, `get`, `list_for_user`, `list_shared_in_workspace`, `update`, `share`, `unshare`, `delete`, `resolve_orphan_owner`); implementations land in US4 phase
  - `apps/control-plane/src/platform/common/tagging/service.py` `TaggingService` facade composing the three; exposes `handle_workspace_archived(workspace_id)` for FR-CC-4 (preserves all tag/label/saved-view rows attached to entities the workspace owns)
- [X] T014 [P] Wire dependency-injection providers in `apps/control-plane/src/platform/common/tagging/dependencies.py`: `get_tag_service`, `get_label_service`, `get_saved_view_service`, `get_tagging_service`, `get_visibility_resolver`, `get_label_expression_evaluator`, `get_label_expression_cache`; reuse `get_audit_chain_service` (UPD-024) and `get_alert_service` (feature 077)
- [X] T015 Mount `common/tagging/router.py` skeleton with **three router groups** at the constitutional REST prefixes (constitution § REST Prefix lines 808–810): `/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*`; admin reserved-namespace label authoring at `/api/v1/admin/labels/reserved` (rule 29 — admin segregation; `require_superadmin` per rule 30); wire onto the FastAPI app at the existing router-mount block in `apps/control-plane/src/platform/main.py:1540–1579`; no middleware added; no APScheduler jobs

---

## Phase 3: User Story 1 — Tag Major Entities and Find Them Across the Platform (P1) 🎯 MVP

**Story goal**: Tags can be attached to and detached from any of the seven major entity types; cross-entity tag search returns visible matches grouped by entity type; entity deletion cascades to tag rows; tag mutation is RBAC-gated and audited.

**Independent test**: Tag five entities of mixed types with `production`; query `GET /api/v1/tags/production/entities` as an authorised user and confirm exactly those five returned grouped by type; as an unauthorised user confirm zero leakage; delete one entity and confirm its tag rows are gone.

### Tests

- [X] T016 [P] [US1] Unit tests `tests/control-plane/unit/common/tagging/test_tag_service.py`: `attach` is idempotent — same `(entity_type, entity_id, tag)` twice creates one row, no error (US1-AS1, FR-511.2); `attach` over the per-entity ceiling raises `TagAttachLimitExceededError` 422; `attach` with a tag that violates `TAG_PATTERN` raises `InvalidTagError`; `attach` for a non-existent entity raises `EntityNotFoundForTagError`; `detach` removes only the specified tag; `cross_entity_search` filters at the SQL layer using `visible_entity_ids_by_type` from the resolver; cascade removes all tag rows for the entity in one transaction
- [X] T017 [P] [US1] Unit tests `tests/control-plane/unit/common/tagging/test_visibility_resolver.py`: each of the seven BCs is queried for its visible-id set; the union is correctly intersected; bound-exceeding cases (> `tagging_cross_entity_search_max_visible_ids`) raise 422 with the documented hint; Principle IV preserved (the resolver never queries entity tables directly — only via service interfaces); seven entity BC service interfaces are mocked individually so the test is independent of those BCs' real implementations
- [X] T018 [P] [US1] Unit tests `tests/control-plane/unit/common/tagging/test_audit_chain_emission_tags.py`: every `attach` and `detach` produces an audit-chain entry via `AuditChainService.append` (`audit/service.py:49`) with `audit_event_source="common_tagging"` and a canonical payload referencing `(entity_type, entity_id, tag, action)`; failed audit-chain writes propagate as 500 (constitution Critical Reminder 30 — never drop an audit event)

### Implementation

- [X] T019 [US1] Implement `apps/control-plane/src/platform/common/tagging/tag_service.py` `TagService` class:
  - `async def attach(*, entity_type, entity_id, tag, requester) -> TagResponse` — validates `entity_type` in `ENTITY_TYPES`; validates tag against `TAG_PATTERN`; checks RBAC by calling the relevant entity BC's "user can mutate this entity" service interface (FR-511.8); checks the per-entity ceiling via `repository.count_tags_for_entity`; calls `repository.insert_tag` (which is idempotent on conflict); emits an audit-chain entry; returns the row
  - `async def detach(*, entity_type, entity_id, tag, requester)` — same RBAC + entity-existence gate; deletes the row; audits
  - `async def list_for_entity(entity_type, entity_id, requester) -> list[TagResponse]` — RBAC scoped to entity visibility
  - `async def cross_entity_search(*, tag, requester, entity_types=None, cursor, limit) -> CrossEntityTagSearchResponse` — calls `visibility_resolver.resolve_visible_entity_ids(requester, entity_types)` first to get the per-(entity_type) visible-id sets; passes them to `repository.list_entities_by_tag` so the SQL WHERE constrains by `entity_type AND entity_id IN (visible_set)` per FR-CC-1; groups results by `entity_type`; returns
  - `async def cascade_on_entity_deletion(entity_type, entity_id)` — invoked by each entity BC's delete path inside that BC's transaction; deletes tag rows AND label rows for the entity (single repository call combining both — see also LabelService); the call is idempotent so a re-run is safe
- [X] T020 [US1] Implement REST endpoints for tags in `common/tagging/router.py`:
  - `POST /api/v1/tags/{entity_type}/{entity_id}` — workspace-member-RBAC; body `TagAttachRequest`; calls `TagService.attach`
  - `DELETE /api/v1/tags/{entity_type}/{entity_id}/{tag}` — workspace-member-RBAC; calls `TagService.detach`
  - `GET /api/v1/tags/{entity_type}/{entity_id}` — workspace-member-RBAC; lists tags on the entity
  - `GET /api/v1/tags/{tag}/entities` — authenticated user; cross-entity search; cursor pagination; supports `?entity_types=workspace,agent` filter; RBAC enforced at the SQL layer per FR-CC-1
  - All mutating endpoints emit audit-chain entries
- [ ] T021 [US1] Wire **cascade-on-delete into all seven entity BCs**:
  - `workspaces/service.py` `WorkspaceService.delete` — call `tagging_service.cascade_on_entity_deletion("workspace", id)` inside the same SQLAlchemy transaction as the workspace soft-delete/hard-delete
  - `registry/service.py` `RegistryService.delete_agent` — call with `("agent", agent_id)`
  - `fleets/service.py` `FleetService.delete` — call with `("fleet", id)`
  - `workflows/service.py` `WorkflowService.delete` — call with `("workflow", id)`
  - `policies/service.py` `PolicyService.delete` — call with `("policy", id)`
  - `trust/service.py` `TrustService.delete_certification` — call with `("certification", id)`
  - `evaluation/service.py` `EvaluationService.delete_run` — call with `("evaluation_run", id)`
  - All seven calls happen INSIDE each BC's existing delete transaction so deletion + tag-cascade are atomic per the plan's cascade contract
- [ ] T022 [US1] Add a `list_visible_<entity>(requester) -> set[UUID]` service-interface method to **each of the seven entity BCs** (additive; preserves existing public method shapes per rule 7):
  - `WorkspaceService.list_visible_workspaces(requester) -> set[UUID]`
  - `RegistryService.list_visible_agents(requester) -> set[UUID]`
  - `FleetService.list_visible_fleets(requester) -> set[UUID]`
  - `WorkflowService.list_visible_workflows(requester) -> set[UUID]`
  - `PolicyService.list_visible_policies(requester) -> set[UUID]`
  - `TrustService.list_visible_certifications(requester) -> set[UUID]`
  - `EvaluationService.list_visible_runs(requester) -> set[UUID]`
  - The seven methods all reuse each BC's existing visibility logic; this task adds the `set[UUID]`-returning shape that the visibility resolver consumes
- [ ] T023 [US1] Add integration test `tests/control-plane/integration/common/tagging/test_tag_attach_per_entity_type.py` (SC-001): for each of the seven `entity_type` strings, attach a tag via the REST endpoint; assert the row persists in `entity_tags`; assert the audit-chain entry is emitted; assert idempotent re-attach is a no-op
- [ ] T024 [US1] Add integration test `tests/control-plane/integration/common/tagging/test_tag_cascade_per_entity_type.py` (SC-003): for each of the seven entity types, create an entity, attach 3 tags, delete the entity, assert all 3 tag rows are gone in the same transaction (no orphan rows)
- [ ] T025 [US1] Add integration test `tests/control-plane/integration/common/tagging/test_cross_entity_tag_search_rbac.py` (SC-002 + SC-014): seed 5 entities of mixed types tagged `production`; create requester A with full visibility, requester B with partial visibility (e.g., only one workspace), requester C with no visibility; assert A sees all 5 grouped by entity_type, B sees only their visible subset, C sees an empty grouped response (NOT a 403 — the RBAC scoping is silent, not enumerative); assert the SQL WHERE in the query log includes the visible-id IN clause (defence-in-depth — verifies SQL-layer enforcement)
- [ ] T026 [US1] Add integration test `tests/control-plane/integration/common/tagging/test_tag_max_per_entity.py` (FR-511.7): attach 50 tags to one entity (the ceiling); attempt to attach a 51st; assert 422 with `TagAttachLimitExceededError` and a clear error message naming the ceiling
- [ ] T027 [US1] Add integration test `tests/control-plane/integration/common/tagging/test_tag_rbac_refusal.py` (FR-511.8): a workspace member without mutation rights on an entity attempts to tag it → 403 with the platform's standard authorization error; the attempt is auditable

**Checkpoint**: US1 deliverable. Tags work uniformly across all seven entity types; cross-entity search is RBAC-correct; cascade-on-delete is atomic; rule 14's mandate is satisfied (the polymorphic substrate exists). MVP shippable here.

---

## Phase 4: User Story 2 — Key-Value Labels with Filtered Listings (P2)

**Story goal**: Labels (key-value, key-unique per entity) attachable to all seven entity types; per-entity-type listings accept `?label.key=value` filters with AND-conjunctive semantics; reserved-namespace writes refused for non-superadmin; updates capture the previous value in the audit trail.

**Independent test**: Attach `env=production` and `tier=critical` to two agents, `env=staging` to a third; query `GET /api/v1/registry/agents?label.env=production&label.tier=critical`; assert exactly the first two are returned; update the third's `env` to `production`; re-query; assert all three returned.

### Tests

- [X] T028 [P] [US2] Unit tests `tests/control-plane/unit/common/tagging/test_label_service.py`: `attach` with new key inserts; `attach` with existing key updates value in place — old value captured in the audit-chain canonical payload per FR-511.10; `attach` with a key matching a reserved namespace prefix raises `ReservedLabelNamespaceError` 403 for non-superadmin requester (FR-511.13); the same write succeeds for a superadmin or service-account requester; `attach` with key violating `LABEL_KEY_PATTERN` raises `InvalidLabelKeyError`; `attach` with value > `MAX_LABEL_VALUE_LEN` raises `LabelValueTooLongError`; per-entity ceiling enforced (FR-511.7 mirror); cascade-on-deletion sweeps label rows alongside tag rows
- [ ] T029 [P] [US2] Unit tests `tests/control-plane/unit/common/tagging/test_label_filter_query.py`: `filter_entities_by_labels` produces the correct AND-conjunctive JOIN SQL; an entity carrying only a subset of the requested labels is NOT returned; the `visible_entity_ids` set constrains the WHERE per FR-CC-1; the JOIN is index-served (assert via `EXPLAIN` parse, not just timing — defence-in-depth on the perf goal)
- [X] T030 [P] [US2] Unit tests `tests/control-plane/unit/common/tagging/test_filter_extension.py`: `parse_tag_label_filters` correctly extracts `?tags=a,b,c` AND `?label.env=production&label.tier=critical` from a FastAPI Request; mixed params are AND-conjunctive across both tag and label dimensions; malformed param shapes (e.g., `label.=production` with empty key) raise a clear 422

### Implementation

- [X] T031 [US2] Implement `apps/control-plane/src/platform/common/tagging/label_service.py` `LabelService` class:
  - `async def attach(*, entity_type, entity_id, key, value, requester) -> LabelResponse` — validates `entity_type` in `ENTITY_TYPES`; validates `key` against `LABEL_KEY_PATTERN` and length; validates `value` length; if `key` starts with any reserved prefix in `RESERVED_LABEL_PREFIXES`, requires `require_superadmin` OR a service-account caller (resolved from the request context); RBAC check on the entity (same `user_can_mutate_entity` interface); checks per-entity ceiling; calls `repository.upsert_label` (returns old value if it was an update); emits audit-chain entry with `{action: "upserted", key, old_value, new_value}` per FR-511.10; returns
  - `async def detach(*, entity_type, entity_id, key, requester)` — same RBAC + reserved-namespace gate; deletes; audits
  - `async def list_for_entity(entity_type, entity_id, requester) -> list[LabelResponse]` — each response carries `is_reserved` computed at read time
  - `async def filter_query(entity_type, label_filters: dict[str,str], requester, cursor, limit) -> set[UUID]` — calls `visibility_resolver.resolve_visible_entity_ids(requester, entity_types=[entity_type])` first; passes the visible-id set to `repository.filter_entities_by_labels` for the JOIN
  - `async def cascade_on_entity_deletion(entity_type, entity_id)` — invoked by each entity BC's delete path in the same transaction (combined with `TagService.cascade_on_entity_deletion` into a single repository call per T010)
- [ ] T032 [US2] Wire **label-filter pass-through into all seven entity BC listing endpoints** (additive query parameters; existing callers see no behaviour change per rule 7):
  - `workspaces/router.py` list-workspaces: accept `?tags=&label.key=` via `filter_extension.parse_tag_label_filters`; on the service side, intersect the existing visibility filter with `LabelService.filter_query`'s result
  - `registry/router.py` `list_agents` at `:147`: accept the same params; `RegistryService.list_agents` at `:371` extends `AgentDiscoveryParams` with `tags` and `labels` fields; the resulting visible-id set is intersected with the JOIN filter (NOT post-filtered in Python — index-served per the perf goal)
  - `fleets/router.py`, `workflows/router.py`, `policies/router.py`, `trust/router.py`, `evaluation/router.py`: same pattern across all seven
  - The brownfield input nominated `registry/services/registry_query_service.py` — that file does not exist; the canonical filter site is `registry/service.py:371 RegistryService.list_agents` (correction recorded in plan + T031's surface)
- [X] T033 [US2] Implement REST endpoints for labels in `common/tagging/router.py`:
  - `POST /api/v1/labels/{entity_type}/{entity_id}` — workspace-member-RBAC; body `LabelAttachRequest`; reserved-namespace keys refused for non-superadmin
  - `DELETE /api/v1/labels/{entity_type}/{entity_id}/{key}` — workspace-member-RBAC; reserved-namespace gate same
  - `GET /api/v1/labels/{entity_type}/{entity_id}` — workspace-member-RBAC; carries `is_reserved` computed at read time
  - `GET /api/v1/labels/keys?entity_type=agent&prefix=env` — autocomplete for the label-key UI (workspace-scoped — only keys present on entities the requester can see)
  - `POST /api/v1/admin/labels/reserved/{entity_type}/{entity_id}` — `require_superadmin`; explicit admin path for reserved-namespace label writes (rule 29) so the operator-RBAC path doesn't have to reason about superadmin vs ordinary; this is the surface features 077/079/080/081 use when they need to write `platform.region=eu-west` etc.
  - All mutating endpoints emit audit-chain entries
- [ ] T034 [US2] Add integration test `tests/control-plane/integration/common/tagging/test_label_filter_per_entity_type.py` (SC-004): for each of the seven entity types, seed entities with mixed labels; query the listing endpoint with `?label.env=production&label.tier=critical`; assert only entities matching ALL specified labels in the requester's visibility are returned; assert the listing latency is within the per-entity-type p95 budget (verified via per-test timing assertion)
- [ ] T035 [US2] Add integration test `tests/control-plane/integration/common/tagging/test_label_upsert_audit_old_value.py` (FR-511.10, SC-005): attach `env=staging`; reattach `env=production`; assert the audit-chain canonical payload for the second call carries `old_value="staging"` and `new_value="production"`; assert exactly ONE row per `(entity_type, entity_id, label_key)` exists at all times
- [ ] T036 [US2] Add integration test `tests/control-plane/integration/common/tagging/test_reserved_namespace_403.py` (SC-006, FR-511.13): non-superadmin attempts `POST /api/v1/labels/agent/{id}` with `key="system.managed"` → 403; same call as superadmin → 200; same call from a service-account caller via the admin endpoint → 200; ordinary key write succeeds for non-superadmin
- [ ] T037 [US2] Add integration test `tests/control-plane/integration/common/tagging/test_label_cascade_per_entity_type.py` (SC-003 — labels variant): for each entity type, create entity + 5 labels; delete entity; assert all 5 label rows gone

**Checkpoint**: US2 deliverable. Labels work uniformly across all seven entity types; AND-conjunctive filtering is index-served; reserved namespaces are server-side enforced; updates capture old value in audit; cascade is atomic.

---

## Phase 5: User Story 3 — Label-Based Expressions in Policy Rules (P3)

**Story goal**: A small typed DSL for label expressions parses, validates, compiles to AST, caches, and evaluates correctly across `=`, `!=`, `AND`, `OR`, `NOT`, `HAS`, parens; integrates into the existing `governance/services/judge_service.py` match-condition flow with NO policy-gateway latency regression; malformed expressions refused at policy save with line+col error pointer.

**Independent test**: Author a policy with expression `env=production`; verify the policy applies to a target carrying that label and not to one without; author a conjunction `env=production AND tier=critical`; verify; submit a malformed expression (e.g., dangling paren); verify the save is refused at policy save time with a clear error.

### Tests

- [X] T038 [P] [US3] Unit tests `tests/control-plane/unit/common/tagging/test_label_expression_parser.py`: full BNF coverage — `key=value`, `key!=value`, `HAS key`, `NOT HAS key`, `expr AND expr`, `expr OR expr`, `NOT expr`, `(expr)`, nested combinations; precedence is `NOT > AND > OR` (documented in `contracts/label-expression-language.md`); malformed inputs raise `LabelExpressionSyntaxError` with `line`, `col`, `token`, `message` populated per FR-511.18; an empty string raises a clear "expression must be non-empty" error rather than panicking
- [X] T039 [P] [US3] Unit tests `tests/control-plane/unit/common/tagging/test_label_expression_evaluator.py` — **property-based with hypothesis**: generate random label dicts and random valid expressions; cross-check evaluator output against an oracle implementation (a slow but obviously-correct Python interpreter of the AST); the property is "evaluator agrees with oracle on every randomly-generated input"; missing-key semantics verified: `key!=value` for missing key → `True` (the key doesn't equal value because it's absent), `HAS key` for missing key → `False`, `NOT HAS key` for missing key → `True`; documented per FR-511.20
- [X] T040 [P] [US3] Unit tests `tests/control-plane/unit/common/tagging/test_label_expression_cache.py`: Redis cache hit on subsequent evaluations of the same `(policy_id, version)` pair; in-process LRU on top serves repeat calls in microseconds (sub-Redis-round-trip per FR-511.19); cache invalidation on policy save (the version increments so the cache key misses); LRU eviction when size exceeds `tagging_label_expression_lru_size`
- [X] T041 [P] [US3] Unit tests `tests/control-plane/unit/common/tagging/test_governance_label_expression_hook.py`: mock `governance/services/judge_service.py`'s match-condition flow at `:39 process_signal` post-chain-resolution (≈ `:49`); inject a policy with a compiled AST; verify the evaluator is called with the target's labels; verify match/miss outcomes; verify a policy with NO expression incurs zero evaluator cost (early-exit on `policy.label_expression is None`)

### Implementation

- [X] T042 [US3] Document the **label-expression grammar** in `apps/control-plane/src/platform/common/tagging/label_expression/grammar.py` (BNF + examples; pure documentation file imported nowhere — keeps the language definition discoverable); the contract file `contracts/label-expression-language.md` is the human-facing version
- [X] T043 [US3] Implement the **hand-rolled recursive-descent parser** at `apps/control-plane/src/platform/common/tagging/label_expression/parser.py`: `tokenize(input: str) -> list[Token]` with `(line, col)` tracking; `parse(tokens) -> ASTNode` recursive descent following the grammar's precedence; on failure raises `LabelExpressionSyntaxError` with the failing token's location (FR-511.18); ≤ 200 LOC keeps the dependency surface clean per the plan's complexity tracking
- [X] T044 [US3] Implement the **typed AST nodes** at `apps/control-plane/src/platform/common/tagging/label_expression/ast.py`: `EqualNode(key, value)`, `NotEqualNode(key, value)`, `HasKeyNode(key)`, `AndNode(left, right)`, `OrNode(left, right)`, `NotNode(child)`, `GroupNode(child)`; each carries an `evaluate(labels: dict[str,str]) -> bool` method; missing-key semantics specified per FR-511.20: `EqualNode` for missing key → `False`, `NotEqualNode` for missing key → `True`, `HasKeyNode` for missing key → `False`, `NotNode(HasKeyNode)` for missing key → `True`
- [X] T045 [US3] Implement the **evaluator** at `apps/control-plane/src/platform/common/tagging/label_expression/evaluator.py`: `async def evaluate(ast, target_labels: dict[str, str]) -> bool` — pure dispatch over the AST; pure function (no I/O); inlinable for performance; the per-call cost is O(AST nodes) which for typical expressions is < 10 nodes
- [X] T046 [US3] Implement the **AST cache** at `apps/control-plane/src/platform/common/tagging/label_expression/cache.py`:
  - `async def get_or_compile(policy_id, version, expression: str | None) -> ASTNode | None` — for `expression is None`, returns `None` (early-exit; zero cost for policies without expressions); checks in-process LRU first; on miss checks Redis under `REDIS_KEY_AST_TEMPLATE.format(...)`; on miss parses the expression, caches both layers, returns
  - `async def invalidate(policy_id, version)` — called by the policies BC on policy save (T048)
  - LRU size from `TaggingSettings.tagging_label_expression_lru_size`
  - The two-layer cache (Redis + in-process LRU) is the FR-511.19 / SC-009 guarantee that gateway p95 doesn't regress
- [X] T047 [US3] **Hook the evaluator into `governance/services/judge_service.py`** at `:19 JudgeService` and `:39 process_signal`:
  - After chain resolution and before verdict generation (≈ `:49`), check whether the matched policy carries a `label_expression`; if yes, call `await label_expression_cache.get_or_compile(policy.id, policy.version, policy.label_expression)` to get the AST; call `await label_expression_evaluator.evaluate(ast, target_labels)`; if `False`, the policy does NOT apply to this signal (skip to next policy in the chain)
  - Target labels are loaded into the existing target context that `process_signal` already passes around; for the seven entity types, `target.labels: dict[str,str]` is populated by the caller via `LabelService.list_for_entity(target.entity_type, target.entity_id)` (cached for the duration of the gateway call to avoid repeat DB hits)
  - The brownfield input named `policies/services/policy_engine.py` — that file does not exist; this is the actual match-condition evaluation site (correction recorded in plan + T047's location)
- [X] T048 [US3] **Hook the cache invalidation into the policies BC's policy-save path**:
  - `policies/service.py` `PolicyService.save_policy` — on successful save, call `await label_expression_cache.invalidate(policy.id, policy.version)`; the next gateway evaluation for that policy will compile-and-cache the new expression
  - On policy save, ALSO call `parser.parse(expression)` synchronously to validate; if parsing raises `LabelExpressionSyntaxError`, re-raise as the BC's existing 422 path so the save is refused with the line+col error pointer per FR-511.18 + SC-008
  - The validation MUST happen at save time (not only at gateway time) — this is the FR-511.18 contract
- [X] T049 [US3] Add REST endpoint `POST /api/v1/labels/expression/validate` in `common/tagging/router.py`: workspace-member-RBAC; body `LabelExpressionValidationRequest`; calls `parser.parse(expression)`; returns `LabelExpressionValidationResponse` with `valid` + optional `error: {line, col, token, message}`; this is the surface the policy authoring UI calls for live validation feedback
- [ ] T050 [US3] Add integration test `tests/control-plane/integration/common/tagging/test_label_expression_in_policy.py` (SC-007): author a policy with expression `env=production`; trigger a signal against an agent carrying `env=production` → verify the policy applies (governance verdict generated); against an agent with `env=staging` or no `env` label → verify the policy does NOT apply; same test for `env=production AND tier=critical` and for `NOT lifecycle=experimental`
- [ ] T051 [US3] Add integration test `tests/control-plane/integration/common/tagging/test_label_expression_malformed_save_refused.py` (SC-008): attempt to save a policy with `env=production AND` (dangling AND); assert the save is refused with `LabelExpressionSyntaxError` 422; assert no half-broken policy persists in PG (the save transaction rolls back before insert); verify the response carries `line`, `col`, `token`, `message`
- [ ] T052 [US3] Add integration test `tests/control-plane/integration/common/tagging/test_policy_gateway_latency_unchanged.py` (SC-009): load-test the policy gateway under a sustained workload; compare pre-feature p95 (baseline measured before T047 lands) and post-feature p95; assert no regression beyond the documented tolerance (e.g., +5%); the in-process LRU + Redis cache path should produce sub-microsecond steady-state per-call cost; record the measurement in the test artifact for future regression detection

**Checkpoint**: US3 deliverable. Label expressions evaluate correctly; policy authoring rejects malformed expressions at save with line+col pointers; gateway latency budget preserved via two-layer cache; the canonical match-condition site is the actual evaluator (`governance/services/judge_service.py`), not the planning input's misnamed `policies/services/policy_engine.py`.

---

## Phase 6: User Story 4 — Saved Views Per User with Workspace Sharing (P4)

**Story goal**: Users save named filter combinations; toggle between personal and shared-with-workspace; orphan-owner case (owner left workspace) handled per documented rule; missing-tag/label references degrade gracefully; FR-576's saved-view affordance is the integration point.

**Independent test**: User A in workspace X saves view "Prod agents"; user B sees only their own views (no leakage); A toggles share; B sees the view; A leaves workspace; the view transfers to a workspace superadmin per the documented rule.

### Tests

- [X] T053 [P] [US4] Unit tests `tests/control-plane/unit/common/tagging/test_saved_view_service.py`: create with valid filters (validated against the entity type's listing filter contract — see T055); list-personal-views returns only the requester's views in the workspace; list-shared-views returns shared views in the requester's workspace (across all owners); update with optimistic concurrency; share → view appears in `list_shared_views` for other workspace members; unshare → view no longer appears for others (still visible to owner); delete removes the row; delete-name-collision raises `SavedViewNameTakenError` 409 per the UNIQUE constraint
- [X] T054 [P] [US4] Unit tests `tests/control-plane/unit/common/tagging/test_saved_view_orphan_owner.py` (SC-012, FR-512.5): user A creates a shared view in workspace X; user A is removed from workspace X; the orphan-owner resolver runs and transfers ownership to the first active superadmin in workspace X (per the documented rule); the new owner sees the view in their personal list; a structured-log notice is emitted for the audit trail; the view's `is_orphan_transferred=True` flag is set so the UI can render the "former member" attribution; if no active superadmin exists in the workspace, the view stays with the original owner but is flagged `is_orphan` so the UI clearly indicates the limbo state; the rule NEVER silently deletes or silently breaks
- [X] T055 [P] [US4] Unit tests `tests/control-plane/unit/common/tagging/test_saved_view_filter_validation.py`: filters JSONB shape is validated against the underlying listing's filter contract per `entity_type` at create time; an unknown filter parameter raises 422; a valid filter shape persists; on apply, a stale tag/label reference returns the standard empty-result presentation, NOT a stack trace per FR-512.6 + SC-011

### Implementation

- [X] T056 [US4] Implement `apps/control-plane/src/platform/common/tagging/saved_view_service.py` `SavedViewService` class:
  - `async def create(*, requester, workspace_id, name, entity_type, filters, shared) -> SavedViewResponse` — validates `entity_type` in `ENTITY_TYPES`; validates `filters` JSONB shape against the entity type's listing filter contract (a small validator registry: each entity type registers its filter Pydantic schema; `SavedViewService` looks it up); RBAC: requester must be a member of `workspace_id`; if `shared=true`, requester must additionally have the workspace's "share saved views" capability (workspace member is sufficient by default; configurable per workspace policy); persists; emits audit-chain entry; returns
  - `async def get(view_id, requester) -> SavedViewResponse` — RBAC: owner OR shared-and-workspace-member; raises 404 with no leakage if requester can't see it
  - `async def list_for_user(requester, entity_type, workspace_id) -> list[SavedViewResponse]` — owner's personal views + workspace's shared views combined; deduped on `id`
  - `async def update(view_id, expected_version, requester, **fields)` — optimistic concurrency
  - `async def share(view_id, requester)` / `async def unshare(view_id, requester)` — owner-only; toggles the `shared` flag; audit-chain entry; FR-512.3 propagation latency (TanStack Query invalidation surfaces it on the frontend within `tagging_saved_view_share_propagation_target_seconds`)
  - `async def delete(view_id, requester)` — owner OR workspace superadmin; audit-chain entry
  - `async def resolve_orphan_owner(workspace_id)` — invoked when a user is removed from a workspace; for each shared view owned by the leaving user in this workspace, `repository.transfer_saved_view_ownership(view_id, new_superadmin_id)` per the documented rule; emits a structured-log notice and an audit-chain entry per transferred view
- [X] T057 [US4] **Hook the orphan-owner resolver into the workspace membership-removal path**:
  - `workspaces/service.py` `WorkspaceService.remove_member` — after the membership row is deleted, call `await saved_view_service.resolve_orphan_owner(workspace_id)` inside the same transaction so the transfer is atomic with the membership removal; this is the canonical trigger for the FR-512.5 rule
- [X] T058 [US4] Implement REST endpoints for saved views in `common/tagging/router.py`:
  - `POST /api/v1/saved-views` — authenticated user; body `SavedViewCreateRequest`
  - `GET /api/v1/saved-views?entity_type=agent&workspace_id=...` — authenticated; returns owner's personal + workspace's shared
  - `GET /api/v1/saved-views/{view_id}` — RBAC scoped per the service
  - `PATCH /api/v1/saved-views/{view_id}` — owner-only; body carries `expected_version`
  - `POST /api/v1/saved-views/{view_id}/share` / `/unshare` — owner-only
  - `DELETE /api/v1/saved-views/{view_id}` — owner OR workspace superadmin
  - All mutating endpoints emit audit-chain entries; FR-512.7
- [ ] T059 [US4] Add integration test `tests/control-plane/integration/common/tagging/test_saved_view_lifecycle.py` (SC-010): user A creates a personal view; user B does NOT see it in their list; A shares; B sees it within `tagging_saved_view_share_propagation_target_seconds` (verified by polling the list endpoint); A unshares; B no longer sees it; A renames; B sees the rename
- [ ] T060 [US4] Add integration test `tests/control-plane/integration/common/tagging/test_saved_view_orphan_owner_transfer.py` (SC-012): user A creates and shares a view in workspace X; X has user S (superadmin); A is removed from X; assert the view's `owner_id` is now S; assert `is_orphan_transferred=True`; assert a structured-log notice was emitted (verified via the test's log-capture fixture); user B in X still sees the view after the transfer
- [ ] T061 [US4] Add integration test `tests/control-plane/integration/common/tagging/test_saved_view_stale_filter_graceful.py` (SC-011, FR-512.6): create a view filtering by `label.team=finance-ops`; delete the team's labels from all entities; apply the view; assert the listing returns an empty result with the standard empty-state presentation (NOT a 500); the view itself still exists
- [ ] T062 [US4] Add integration test `tests/control-plane/integration/common/tagging/test_saved_view_audit_chain.py` (SC-013 partial — saved-view variant): every create / update / share / unshare / delete produces an audit-chain entry with the appropriate canonical payload

**Checkpoint**: US4 deliverable. Saved views are personal-by-default with explicit-share semantics; the orphan-owner case is handled per a documented, audited, surfaced-not-silent rule; missing tags/labels degrade to empty results, not crashes; FR-576's affordance is the integration point.

---

## Phase 7: Frontend `<TagEditor>` / `<LabelEditor>` / `<SavedViewPicker>` integrated into 7 list pages

**Story goal**: Surface tag/label/saved-view affordances uniformly across the seven existing list pages and the platform shell. Satisfies rule 45, FR-CC-5, and the FR-576 admin-data-table integration point.

- [X] T063 [P] Create `apps/web/lib/api/tagging.ts`: typed wrappers over `/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*`, `/api/v1/admin/labels/reserved`; reuse the shared `apiClient` and JWT injection from `lib/api.ts`; TanStack Query hook factories `useEntityTags`, `useEntityLabels`, `useTagAttach`, `useTagDetach`, `useLabelUpsert`, `useLabelDetach`, `useCrossEntityTagSearch`, `useSavedViews`, `useSavedViewCreate`, `useSavedViewShare`, `useLabelExpressionValidate` (debounced for the policy-authoring live-validation feedback)
- [X] T064 [P] Create `apps/web/components/features/tagging/`:
  - `TagEditor.tsx` — chip input with autocomplete; calls the autocomplete endpoint scoped to the workspace's existing tags; per-entity ceiling enforced client-side with hint at limit
  - `LabelEditor.tsx` — key-value pair editor; reserved-namespace keys (matching `system.*` / `platform.*`) shown as read-only with a `<ReservedLabelBadge>` for non-superadmin; superadmin sees them editable
  - `TagFilterBar.tsx` — toolbar component parsing `?tags=` from the URL; chip-style display; click-to-remove; AND-conjunctive
  - `LabelFilterPopover.tsx` — key/value selector with values autocomplete (calls `GET /api/v1/labels/keys?prefix=...`); AND-conjunctive
  - `SavedViewPicker.tsx` — dropdown listing the user's personal views + the workspace's shared views; "Save current view" CTA; "Share with workspace" toggle on a saved view; orphan-transferred views display with a "former member" attribution per FR-512.5
  - `SavedViewSaveDialog.tsx` — name input + share toggle + entity-type confirmation
  - `CrossEntityTagSearch.tsx` — extends the platform shell's command palette (existing cmd+K via `cmdk` per feature 015) with a `tag:` prefix; `tag:production` returns visible entities grouped by type
  - `LabelExpressionEditor.tsx` — Monaco-Editor-backed input for label expressions (in policy authoring); calls `useLabelExpressionValidate` on debounced input; renders syntax errors inline with the line+col pointer per FR-511.18
  - `ReservedLabelBadge.tsx` — visual indicator for reserved-namespace labels
- [ ] T065 [US-FE] Integrate the components into the **seven existing list pages**:
  - `apps/web/app/(main)/agents/page.tsx` — toolbar carries `<SavedViewPicker entityType="agent" />`, `<TagFilterBar />`, `<LabelFilterPopover />`; agent detail row shows `<TagEditor>` and `<LabelEditor>`
  - `fleet/page.tsx`
  - `workflow-editor-monitor/page.tsx`
  - `agent-management/page.tsx` (the registry view)
  - the policies admin page (under `app/(main)/admin/...`)
  - `trust-workbench/` certifications page
  - the evaluation runs page
  - Each page calls the same shared components — uniform UX across all seven entity types
- [ ] T066 [US-FE] Extend the **policy authoring UI** to embed `<LabelExpressionEditor>` for the new `label_expression` field; live validation feedback as the user types (debounced 300ms); on save, the backend's parser validation is the source of truth; client-side validation is a UX hint only (FR-511.18 + SC-008)
- [ ] T067 [P] [US-FE] Vitest + RTL component tests:
  - `TagEditor`: per-entity ceiling client-side hint; idempotent re-add visually a no-op; pattern violation rejected client-side with the same regex as `TAG_PATTERN`
  - `LabelEditor`: reserved-namespace keys disabled for non-superadmin (badge tooltip explains); upsert flow shows optimistic update with rollback on 403/422
  - `SavedViewPicker`: personal vs shared distinction visually clear (matches rule 47 — workspace-vs-platform scope distinction); orphan-transferred attribution rendered when applicable
  - `LabelExpressionEditor`: malformed input shows the line+col error inline within 300ms; valid input shows a green check
  - `CrossEntityTagSearch`: cmd+K palette responds to `tag:` prefix; results grouped by entity type; click-through navigates to the entity detail view
- [ ] T068 [US-FE] Playwright E2E test `apps/web/tests/e2e/tagging.spec.ts`: workspace-member happy path — log in → navigate to `/agents` → tag an agent `production` → save the current view (with `label.env=production` filter) → share the view with the workspace → log in as a different workspace member → see the shared view in the picker → apply the view → see the filtered list; navigate to the policy authoring page → enter a label expression → see live validation feedback → save the policy → verify the gateway evaluation matches/misses the target correctly

**Checkpoint**: Rule 45 + FR-CC-5 satisfied; tag/label/saved-view affordances are uniform across all seven list pages; FR-576's saved-view integration point exists for the admin data-table standards feature.

---

## Phase 8: Polish & Cross-Cutting

- [X] T069 [P] Extend the existing `deploy/helm/observability/templates/dashboards/platform-overview.yaml` (NOT a new dashboard ConfigMap — declared variance from rule 24 in plan): additive panels for tag mutation rate (per-second), label mutation rate (per-second by `is_reserved` boolean), cross-entity tag search latency (p50 / p95 / p99 graph), compiled-AST cache hit rate (Redis hits + LRU hits + misses by stacked area), saved-view share-propagation latency. Labels limited to `service`, `bounded_context=common-tagging`, `level` (rule 22). The variance rationale (`common/` is shared substrate, not a BC, so no per-BC dashboard) is included as a panel description so future dashboard reviewers see it
- [X] T070 [P] Add OpenAPI tags `common-tagging-tags`, `common-tagging-labels`, `common-tagging-saved-views`, `common-tagging-admin-labels`, `common-tagging-label-expression` and ensure all `/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*`, `/api/v1/admin/labels/reserved/*` routers carry them
- [ ] T071 [P] **Extend three existing E2E journeys** rather than create a parallel suite (declared variance from rule 25; rule 28 — extend, do not parallel):
  - `tests/e2e/journeys/test_registry_discovery_journey.py` — extend to tag agents, label them, filter the marketplace listing by `?label.env=production`
  - `tests/e2e/journeys/test_policy_authoring_journey.py` — extend to author a policy with the label expression `env=production AND tier=critical`; verify the gateway match/miss
  - `tests/e2e/journeys/test_operator_dashboard_journey.py` — extend to save a view as user A, share with workspace, apply as user B, remove A from workspace, verify the orphan-transfer
- [X] T072 [P] Run `ruff check apps/control-plane/src/platform/common/tagging` and `mypy --strict apps/control-plane/src/platform/common/tagging`; resolve all findings; assert no `os.getenv` for `*_SECRET` / `*_API_KEY` / `*_TOKEN` outside SecretProvider files (rule 39 — none expected; verify)
- [ ] T073 [P] Run `pytest tests/control-plane/unit/common/tagging tests/control-plane/integration/common/tagging -q`; verify ≥ 95% line coverage on `apps/control-plane/src/platform/common/tagging/` (constitution § Quality Gates)
- [ ] T074 [P] Run the **property-based label-expression evaluator test** with `hypothesis --max-examples=10000` (one-time deeper run pre-merge; CI uses 1000) to maximise coverage of the missing-key semantics edge cases per FR-511.20
- [X] T075 [P] **Document the label-expression DSL** in the docs site (under `docs/reference/`): the BNF, the operator precedence, the missing-key semantics table, the worked examples; the policy authoring UI links to this page from the `<LabelExpressionEditor>` help icon
- [X] T076 [P] **Document the tag normalisation rules** and the **reserved-namespace policy** in the docs site: the case-sensitivity decision, the allowed character set, the per-entity ceiling, the reserved prefixes, the superadmin-only override path
- [ ] T077 [P] Smoke-run the `quickstart.md` walkthrough (tag an agent → label a policy → author a label-expression policy → save a view → share it → apply it as a different user) against a local control plane; capture deviations and update `quickstart.md` accordingly
- [X] T078 Update `CLAUDE.md` Recent Changes via `bash .specify/scripts/bash/update-agent-context.sh` so future agent context reflects this substrate; the entry must call out (a) **`common/tagging/` is shared substrate, NOT a bounded context** (so future planners don't try to "fix" the rule-24/25 variances), (b) **the brownfield input named two non-existent files (`policies/services/policy_engine.py`, `registry/services/registry_query_service.py`) — the canonical sites are `governance/services/judge_service.py:19` and `registry/service.py:371`** (so future agents don't try to "fix" the missing files), (c) **the seventh entity is `evaluation_runs`, NOT `evaluation_suites`** as the input said (so future planners use the real table name), (d) **cascade-on-delete is application-layer, not FK CASCADE** — the polymorphic shape forbids a typed FK; each entity BC's delete path is the canonical cascade trigger

---

## Dependencies

```
Phase 1 (Setup) ──▶ Phase 2 (Foundational) ──▶ Phase 3 (US1, P1) ──▶ Checkpoint MVP (rule 14 satisfied)
                                                       │
                                                       ▼
                                              ┌────────────────────────────┐
                                              │ Phase 4 US2 (P2)           │ — depends on US1 (labels reuse the
                                              │   (labels + filtering)     │   visibility resolver, cascade
                                              │                            │   pair, audit emission pattern)
                                              │                            │
                                              │ Phase 5 US3 (P3)           │ — depends on US2 (label values must
                                              │   (label expressions       │   exist before expressions can
                                              │    in policies)            │   evaluate them)
                                              │                            │
                                              │ Phase 6 US4 (P4)           │ — depends on US1 + US2 (saved views
                                              │   (saved views)            │   reference tags AND labels in
                                              │                            │   their filter shape)
                                              └────────────────────────────┘
                                                       │
                                                       ▼
                                              Phase 7 (Frontend across 7 list pages)
                                                       │
                                                       ▼
                                                Phase 8 (Polish)
```

**MVP scope**: Phase 1 + Phase 2 + Phase 3 = 27 tasks. Delivers the polymorphic tag substrate end-to-end across all seven entity types with cross-entity search + cascade + RBAC. Constitution rule 14's mandate is satisfied here. Labels (US2), expressions (US3), and saved views (US4) ship in subsequent waves.

**Parallel opportunities**:
- Phase 1: T002 ∥ T003 ∥ T004 (independent files).
- Phase 2: T006 ∥ T007 ∥ T008 ∥ T009 ∥ T011 ∥ T012 ∥ T014 (independent files); T005 sequential (single migration); T010 / T013 / T015 sequential after their inputs.
- Phase 3: T016 ∥ T017 ∥ T018 (test-only); T019 sequential (TagService); T020 (REST) parallel to T021 (cascade hooks across 7 BCs — themselves parallelizable across two devs as Workspaces+Registry+Fleets+Workflows vs Policies+Trust+Evaluation) and T022 (visibility methods across 7 BCs — same parallel split); T023 / T024 / T025 / T026 / T027 mostly parallel after the implementation lands.
- Phase 4: T028 ∥ T029 ∥ T030 (test-only); T031 sequential (LabelService); T032 (7 entity-BC integrations — parallelizable across two devs); T033 (REST) parallel to T034 / T035 / T036 / T037.
- Phase 5: T038 ∥ T039 ∥ T040 ∥ T041 (test-only — T039 is property-based; T040 / T041 mock the Redis cache and the governance hook respectively); T042 / T043 / T044 / T045 / T046 (parser + AST + evaluator + cache — independent files; can parallelize); T047 sequential (governance hook); T048 sequential (policies BC hook); T049 / T050 / T051 / T052 mostly parallel after T047 + T048.
- Phase 6: T053 ∥ T054 ∥ T055 (test-only); T056 sequential (SavedViewService); T057 (workspace hook) sequential after T056; T058 (REST) parallel to T059 / T060 / T061 / T062.
- Phase 7: T063 ∥ T064 ∥ T067 (lib + components + tests, fully parallel); T065 (7 list-page integrations — parallelizable across two devs as in Phases 3/4) + T066 (policy authoring) sequential after T063 + T064; T068 sequential at the end.
- Phase 8: T069 ∥ T070 ∥ T071 ∥ T072 ∥ T073 ∥ T074 ∥ T075 ∥ T076 ∥ T077 (independent surfaces); T078 last.

---

## Implementation strategy

1. **Wave 10A (MVP — US1, the substrate floor)** — Phases 1, 2, 3. Two backend devs (split the 7 entity-BC cascade hooks + the 7 visibility-method additions). Delivers the polymorphic tag substrate; constitution rule 14's mandate is satisfied. After Wave 10A, every existing entity is taggable + searchable across types, cascade is atomic, RBAC is enforced at the SQL layer.
2. **Wave 10B (US2 — labels)** — Phase 4. One backend dev. The 7 entity-BC listing extensions (T032) are repetitive but small; the highest-risk task is T031 (reserved-namespace enforcement + the upsert audit-old-value semantics) — pair-review.
3. **Wave 10C (US3 — label expressions)** — Phase 5. One backend dev (with code-review attention from a governance/policies SME). The DSL parser + AST is small but precision matters (T038–T044); the gateway-latency-no-regression guarantee (T046 + T052) is the hardest non-functional constraint.
4. **Wave 10D (US4 — saved views) + Frontend** — Phases 6 + 7. One backend dev for Phase 6; one frontend dev for Phase 7. Phase 7 can start as soon as the Phase 4 + 5 REST contracts merge (it doesn't need to wait for Phase 6's saved-view backend if the saved-view picker is the last component to land).
5. **Wave 10E (Polish)** — Phase 8. Dashboard panel additions (rule 24 variance), OpenAPI tags, journey extensions (rule 25 variance), lint/types/coverage gates, property-based deeper run, docs-site DSL + reserved-namespace documentation, smoke-run, agent-context update.

**Constitution coverage matrix**:

| Rule / AD | Where applied | Tasks |
|---|---|---|
| 1, 4, 5 (brownfield) | All — extends `common/`, 7 entity BCs additively, `governance/services/judge_service.py`, `policies/service.py` save path | T010, T013, T021, T022, T032, T047, T048, T057 |
| 2 (Alembic only) | Phase 2 | T005 |
| 6 (additive enums) | Phase 1 | T002 (string constants, no enum mutation) |
| 7 (backwards compat) | Phase 3, 4 | T020, T032, T033 (filter parameters are optional; existing callers see no change) |
| 8 (feature flags) | N/A — substrate is not gated; expression evaluation is per-policy presence | — |
| 9 (PII / sensitive op audit) | Phase 3, 4, 6 | T019, T031, T056 (every mutation audited via `AuditChainService.append`) |
| 14 (every new entity supports tags + labels) | Phase 1, 2, 3 | T002, T005 — this feature IS the canonical implementation that rule 14 presumes exists |
| 18, AD-21 (residency at query time, region first-class) | N/A — tag/label rows replicate via parent entity's existing path (feature 081 contract) | — |
| 20, 22 (structured JSON logs, low-cardinality labels) | All Python files | T069 (Loki label policing on the dashboard panels) |
| 21 (correlation IDs context-managed) | All endpoints | Audit-chain entries inherit CorrelationContext from the request middleware |
| 23, 31, 40 (no secrets in logs) | N/A — feature handles no secrets | — |
| 24 (every BC dashboard) | ⚠️ Variance — declared in plan; T069 extends `platform-overview.yaml` instead | T069 |
| 25, 28 (every BC E2E + journey crossing; extend not parallel) | ⚠️ Variance — declared in plan; T071 extends three existing journeys | T071 |
| 29, 30 (admin endpoint segregation, admin role gates) | Phase 4 | T033 (`/api/v1/admin/labels/reserved` segregated; `require_superadmin`) |
| 32 (audit chain on config changes) | Phase 3, 4, 6 | T019, T031, T056 |
| 36 (UX-impacting FR documented) | Phase 8 | T075 (DSL doc), T076 (normalisation + reserved-namespace doc), T077 (quickstart) |
| 39 (every secret resolves via SecretProvider) | N/A — no secrets | — |
| 45 (backend has UI) | Phase 7 | T065, T066 |
| 47 (workspace-scoped vs platform-scoped) | Phase 4, 6, 7 | T031 (reserved-namespace = platform-scoped); T056 (saved view shared = workspace-scoped); T064 (UI distinguishes the two scopes) |
| Principle I (modular monolith) | All | All work in the Python control plane |
| Principle III (dedicated stores) | Phase 2 | T005 (PG for relational truth); T002 + T046 (Redis for AST cache) |
| Principle IV (no cross-BC table access) | Phase 2, 3 | T011 (visibility resolver calls service interfaces, never tables); T021 (cascade hook is invoked BY each BC inside its own transaction — `common/tagging/` does not query entity tables itself) |
| Constitutional REST prefixes already declared | Phase 2, 3, 4, 6 | T015, T020, T033, T058 (`/api/v1/tags/*`, `/api/v1/labels/*`, `/api/v1/saved-views/*` per constitution lines 808–810) |

---

## Notes

- The `[Story]` tag maps each task to its user story (US1, US2, US3, US4, or US-FE for frontend tasks that span stories) so independent delivery is preserved.
- Constitution rule 14 explicitly mandates this substrate. T002 + T005 + T019 + T031 are the canonical implementation; future BCs adopting tags/labels register their `entity_type` string in `ENTITY_TYPES` and add the filter pass-through to their listing endpoint — no schema migration, no per-entity column.
- The **brownfield input named three non-existent file targets** that future planners might re-introduce by mistake; T078 ensures CLAUDE.md captures the corrections:
  - `policies/services/policy_engine.py` — does NOT exist; canonical match-condition evaluator is `governance/services/judge_service.py:19 JudgeService.process_signal` at `:39` (the hook lands at ≈ `:49`)
  - `registry/services/registry_query_service.py` — does NOT exist; canonical filter site is `registry/service.py:371 RegistryService.list_agents`
  - `evaluation_suites` — the actual table is `evaluation_runs` at `evaluation/models.py:175 EvaluationRun`
- **Two declared variances** from constitution rules 24 and 25 (in the Constitution Check table of the plan + the rationale paragraphs in T069 and T071): `common/tagging/` is shared substrate, not a BC, so the rules' letter does not apply; their spirit is preserved by extending the existing platform-overview dashboard and three existing journeys per rule 28's "extend, do not parallel" principle.
- **Cascade-on-entity-delete is application-layer**, NOT FK + ON DELETE CASCADE. The polymorphic `(entity_type, entity_id)` shape forbids a typed FK. Each entity BC's existing delete path (T021) is the canonical cascade trigger, called inside that BC's own transaction.
- **The two-layer cache** (Redis + in-process LRU) for compiled label-expression ASTs is the FR-511.19 / SC-009 guarantee that the policy gateway p95 doesn't regress. Skipping either layer regresses (Redis-only adds round-trip; LRU-only fails to invalidate across replicas).
- **The seven entity types** at v1 are: `workspace`, `agent`, `fleet`, `workflow`, `policy`, `certification`, `evaluation_run`. Adding more is a future-additive change governed by rule 14 — register the new type in `ENTITY_TYPES`, add `list_visible_<entity>(requester)` to that BC's service, add the filter pass-through to its listing endpoint, add the cascade call to its delete path. No schema migration.
- Migration `065_tags_labels_saved_views.py` MUST rebase to the current alembic head at merge time (latest at branch cut: `064_multi_region_ops` from feature 081).
- **Effort estimate disconnect**: the planning input said 2 SP / 1 day; the plan flagged this is materially understated (~5–8× the input). The Wave 10A–10E split is the recommended descope path if the work spans more than one push. **Wave 10A alone (Phases 1–3, 27 tasks) satisfies rule 14's mandate** — tagging and cross-entity search; labels, expressions, and saved views are valuable but not strictly required for rule-14 compliance.
