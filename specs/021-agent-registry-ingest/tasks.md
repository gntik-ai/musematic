# Tasks: Agent Registry and Ingest

**Input**: Design documents from `specs/021-agent-registry-ingest/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/registry-api.md ✓, quickstart.md ✓

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US6)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create package skeleton and Alembic migration before any story work begins.

- [x] T001 Create `apps/control-plane/src/platform/registry/` package with stub `__init__.py`, `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `state_machine.py`, `package_validator.py`, `index_worker.py`, `registry_opensearch_setup.py`, `registry_qdrant_setup.py`
- [x] T002 Create Alembic migration `apps/control-plane/migrations/versions/006_registry_tables.py` — 5 tables: `registry_namespaces`, `registry_agent_profiles`, `registry_agent_revisions`, `registry_maturity_records`, `registry_lifecycle_audit` with all unique constraints and indexes from data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before any user story can be implemented.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Implement all exception classes in `apps/control-plane/src/platform/registry/exceptions.py` — `RegistryError`, `FQNConflictError`, `NamespaceConflictError`, `PackageValidationError` (with `error_type` + `field` fields), `InvalidTransitionError`, `AgentNotFoundError`, `WorkspaceAuthorizationError`, `RegistryStoreUnavailableError`
- [x] T004 Implement `apps/control-plane/src/platform/registry/state_machine.py` — `VALID_REGISTRY_TRANSITIONS` dict, `EVENT_TRANSITIONS` set, `is_valid_transition(current: LifecycleStatus, target: LifecycleStatus) -> bool`, `get_valid_transitions(current: LifecycleStatus) -> set[LifecycleStatus]`
- [x] T005 [P] Implement `apps/control-plane/src/platform/registry/registry_opensearch_setup.py` — idempotent `create_marketplace_agents_index()` with full mappings from data-model.md (fqn keyword, purpose text with purpose_analyzer, tags keyword array, role_types keyword array, maturity_level integer, status keyword, workspace_id keyword)
- [x] T006 [P] Implement `apps/control-plane/src/platform/registry/registry_qdrant_setup.py` — idempotent `create_agent_embeddings_collection()` using `settings.embedding_vector_size` (default 1536), `Distance.COSINE`, payload fields: fqn, workspace_id, namespace, status
- [x] T007 [P] Implement `apps/control-plane/src/platform/registry/package_validator.py` — `PackageValidator` class with `validate(package_bytes, filename) -> ValidationResult`; 8-step pipeline: (1) extension check `.tar.gz`/`.zip`, (2) size limit check (50MB configurable), (3) extract to isolated `tempfile.mkdtemp()`, (4) path traversal check — `Path(tmpdir / member).resolve().is_relative_to(tmpdir)` for every member, (5) symlink rejection, (6) file count/depth sanity limits, (7) required manifest file (`manifest.yaml` or `manifest.json`) presence, (8) `AgentManifest` Pydantic parse + SHA-256 `hashlib.sha256(package_bytes).hexdigest()`; `ValidationResult` dataclass with `sha256_digest`, `manifest: AgentManifest`, `temp_dir: Path`

**Checkpoint**: Foundation ready — user story implementation can now begin.

---

## Phase 3: User Story 1 — Namespace Management and Agent Registration (Priority: P1) 🎯 MVP

**Goal**: Administrator creates namespaces; developer uploads agent packages; system validates, stores, and registers agents with immutable revisions and FQN.

**Independent Test**: Create namespace "test-ns" → upload valid package → verify FQN "test-ns:my-agent", status "draft", revision with SHA-256 digest created → upload second version → verify second revision created → attempt path traversal package → verify 422 `path_traversal` → attempt missing `purpose` manifest → verify 422 `manifest_invalid`.

- [x] T008 [P] [US1] Implement all SQLAlchemy models and enums in `apps/control-plane/src/platform/registry/models.py` — `LifecycleStatus`, `AgentRoleType`, `MaturityLevel`, `AssessmentMethod`, `EmbeddingStatus` enums + `AgentNamespace`, `AgentProfile`, `AgentRevision`, `AgentMaturityRecord`, `LifecycleAuditEntry` models with all columns, constraints, and indexes from data-model.md
- [x] T009 [P] [US1] Implement all Pydantic schemas in `apps/control-plane/src/platform/registry/schemas.py` — `AgentManifest` (with `custom_role_requires_description` validator), `NamespaceCreate`, `AgentUploadParams`, `AgentPatch`, `LifecycleTransitionRequest`, `MaturityUpdateRequest`, `AgentDiscoveryParams`, `NamespaceResponse`, `AgentRevisionResponse`, `AgentProfileResponse`, `AgentUploadResponse`, `AgentListResponse`, `LifecycleAuditResponse`, `PackageValidationError`
- [x] T010 [US1] Implement `apps/control-plane/src/platform/registry/repository.py` — `RegistryRepository` with: `create_namespace()`, `get_namespace_by_name()`, `list_namespaces()`, `delete_namespace()`, `upsert_agent_profile()` (INSERT … ON CONFLICT DO UPDATE for mutable fields), `get_agent_by_id()`, `get_agent_by_fqn()`, `list_agents_by_workspace()`, `insert_revision()` (no UPDATE method — enforces immutability), `list_revisions()`, `insert_maturity_record()`, `insert_lifecycle_audit()`, `get_agents_needing_reindex()`
- [x] T011 [US1] Implement `RegistryService.create_namespace()`, `upload_agent()`, `get_agent()`, `list_namespaces()`, `delete_namespace()`, `list_revisions()` in `apps/control-plane/src/platform/registry/service.py` — `upload_agent()` must: call `PackageValidator.validate()`, upload bytes to MinIO (`{workspace_id}/{namespace}/{local_name}/{revision_id}/package.tar.gz`), upsert `AgentProfile`, insert `AgentRevision`, sync-index to OpenSearch, dispatch async embedding task, call `publish_agent_created()`; compensating MinIO delete on PostgreSQL failure
- [x] T012 [P] [US1] Implement `apps/control-plane/src/platform/registry/events.py` — `AgentCreatedPayload` Pydantic model + `publish_agent_created(producer, payload, correlation)` using canonical `EventEnvelope` on topic `registry.events`
- [x] T013 [US1] Implement `apps/control-plane/src/platform/registry/dependencies.py` — `get_registry_service()` async DI factory injecting `RegistryRepository`, `ObjectStorageClient`, `OpenSearchClient`, `QdrantClient`, `WorkspacesService`, `KafkaProducer`
- [x] T014 [US1] Implement namespace and upload endpoints in `apps/control-plane/src/platform/registry/router.py` — `POST /api/v1/namespaces`, `GET /api/v1/namespaces`, `DELETE /api/v1/namespaces/{namespace_id}`, `POST /api/v1/agents/upload` (multipart: `namespace_name` form field + `package` UploadFile), `GET /api/v1/agents/{agent_id}`, `GET /api/v1/agents/{agent_id}/revisions`; all endpoints enforce `X-Workspace-ID` workspace membership

**Checkpoint**: Namespace creation, package upload with full validation, and revision listing are functional and independently testable.

---

## Phase 4: User Story 2 — Agent Discovery and FQN Resolution (Priority: P1)

**Goal**: Users and agents find registered agents by exact FQN, FQN pattern, or keyword. Discovery results filtered by visibility configuration.

**Independent Test**: Register "ns-a:agent-1" and "ns-b:agent-2" (both published) → resolve exact FQN → verify 200 within 200ms → query `fqn_pattern=ns-a:*` → verify only ns-a agent returned → search `keyword=agent` → verify keyword match → configure agent with `visibility_agents=[]` → query as that agent → verify 0 results.

- [x] T015 [US2] Add `search_by_keyword()` to `apps/control-plane/src/platform/registry/repository.py` — OpenSearch query against `marketplace-agents` index using multi_match on `name`, `purpose`, `approach`, `tags`; add `get_by_fqn()` fast-path index lookup
- [x] T016 [US2] Implement `RegistryService.resolve_fqn()` and `RegistryService.list_agents()` in `apps/control-plane/src/platform/registry/service.py` — `list_agents()` applies FQN pattern matching via `re.fullmatch()` on each candidate; effective visibility = union of `requesting_agent.visibility_agents` patterns + `WorkspaceVisibilityGrant` records from `workspaces_service.get_workspace_visibility_grants(workspace_id)`; human user queries bypass agent-level visibility and apply workspace membership filtering only
- [x] T017 [US2] Add discovery endpoints to `apps/control-plane/src/platform/registry/router.py` — `GET /api/v1/agents/resolve/{fqn}` (FQN path param, workspace-scoped, ≤200ms), `GET /api/v1/agents` (query params: `status`, `maturity_min`, `fqn_pattern`, `keyword`, `limit`, `offset`)

**Checkpoint**: FQN resolution, pattern matching, and keyword search are functional with visibility filtering applied.

---

## Phase 5: User Story 3 — Lifecycle State Management (Priority: P1)

**Goal**: Agents move through defined lifecycle states; every transition is audited; events emitted for published and deprecated transitions.

**Independent Test**: Register agent (draft) → `draft → deprecated` fails with 409 → `draft → validated` succeeds with audit record → `validated → published` emits `registry.agent.published` event → `published → disabled` succeeds → `disabled → published` succeeds → `published → deprecated` emits `registry.agent.deprecated` → `deprecated → archived` succeeds → GET lifecycle-audit shows all transitions.

- [x] T018 [US3] Implement `RegistryService.transition_lifecycle()` in `apps/control-plane/src/platform/registry/service.py` — call `is_valid_transition()`, raise `InvalidTransitionError` with valid transitions listed if invalid, update `AgentProfile.status`, insert `LifecycleAuditEntry`, emit Kafka event for `EVENT_TRANSITIONS` (published + deprecated)
- [x] T019 [P] [US3] Add `AgentPublishedPayload`, `AgentDeprecatedPayload`, `publish_agent_published()`, `publish_agent_deprecated()` to `apps/control-plane/src/platform/registry/events.py`
- [x] T020 [US3] Add lifecycle endpoints to `apps/control-plane/src/platform/registry/router.py` — `POST /api/v1/agents/{agent_id}/transition`, `GET /api/v1/agents/{agent_id}/lifecycle-audit`

**Checkpoint**: All lifecycle transitions enforced, audited, and event-emitting. All P1 user stories complete.

---

## Phase 6: User Story 4 — Maturity Classification (Priority: P2)

**Goal**: Agents carry a maturity level (0–3) with full audit history; filterable in discovery.

**Independent Test**: Upload agent (default maturity 0) → verify maturity_level=0 → POST `/maturity` with level=2 → verify profile updated + `AgentMaturityRecord` inserted → GET `/agents?maturity_min=2` → verify only level 2+ agents returned → GET maturity record via direct DB query → verify previous_level=0, new_level=2, assessment_method=`system_assessed`.

- [x] T021 [US4] Implement `RegistryService.update_maturity()` in `apps/control-plane/src/platform/registry/service.py` — update `AgentProfile.maturity_level`, insert `AgentMaturityRecord` with previous_level, new_level, `AssessmentMethod.SYSTEM_ASSESSED`, actor_id, reason
- [x] T022 [US4] Add maturity endpoint to `apps/control-plane/src/platform/registry/router.py` — `POST /api/v1/agents/{agent_id}/maturity` accepting `MaturityUpdateRequest`

**Checkpoint**: Maturity classification and audit history functional.

---

## Phase 7: User Story 5 — Visibility Configuration Management (Priority: P2)

**Goal**: Administrators configure per-agent visibility patterns; workspace grants override defaults; changes take effect immediately.

**Independent Test**: Register agent with default `visibility_agents=[]` → verify 0 discovery results as that agent → PATCH visibility to `["ns-a:*"]` → verify only ns-a agents visible → PATCH with invalid regex → verify 422 → GET workspace grants → verify union applied in next discovery query.

- [x] T023 [US5] Implement `RegistryService.patch_agent()` in `apps/control-plane/src/platform/registry/service.py` — update mutable fields (display_name, tags, approach, role_types, custom_role_description, visibility_agents, visibility_tools); validate each pattern in `visibility_agents` and `visibility_tools` using `re.compile()`, raising `RegistryError` with `error_type="invalid_visibility_pattern"` on failure; implement `resolve_effective_visibility(agent_id, workspace_id) -> EffectiveVisibility` internal interface
- [x] T024 [US5] Add PATCH endpoint to `apps/control-plane/src/platform/registry/router.py` — `PATCH /api/v1/agents/{agent_id}` accepting `AgentPatch`

**Checkpoint**: Visibility configuration and effective visibility resolution functional.

---

## Phase 8: User Story 6 — Agent Update and Revision History (Priority: P3)

**Goal**: Metadata updates do not create revisions; revision history is immutable and fully browsable.

**Independent Test**: Upload agent → PATCH display_name → verify no new revision created → upload new version → verify new revision → list revisions → verify chronological order with correct digests → attempt to call any UPDATE SQL on `registry_agent_revisions` → verify no such method exists in repository.

- [x] T025 [P] [US6] Enforce revision immutability in `apps/control-plane/src/platform/registry/repository.py` — verify `RegistryRepository` has NO update method for `AgentRevision`; add `get_revision_by_id()` and ensure `list_revisions()` orders by `created_at ASC`
- [x] T026 [US6] Wire mutable metadata fields into `RegistryService.patch_agent()` in `apps/control-plane/src/platform/registry/service.py` — confirm `upload_agent()` increments revision count but does NOT change existing revisions; add explicit guard that raises `RegistryError` if caller attempts to update digest or manifest_snapshot

**Checkpoint**: All 6 user stories complete. Full feature functional end-to-end.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Background workers, integration wiring, tests, and quality gates.

- [x] T027 Implement `apps/control-plane/src/platform/registry/index_worker.py` — `RegistryIndexWorker` background task: poll `registry_agent_profiles WHERE needs_reindex = true` every 30 seconds, re-index each agent to OpenSearch, set `needs_reindex = false` on success, log failures without crashing the worker loop
- [x] T028 [P] Add async embedding background task in `apps/control-plane/src/platform/registry/service.py` — `_generate_embedding_async(agent_profile_id)`: fetch purpose + approach, POST to `settings.embedding_api_url` via `httpx.AsyncClient`, upsert vector into Qdrant with `agent_profile_id` as point ID and payload `{fqn, workspace_id, namespace, status}`, update `embedding_status` to `complete` or `failed`
- [x] T029 Mount registry router in `apps/control-plane/src/platform/api/__init__.py` — include `registry.router` with prefix `/api/v1`
- [x] T030 [P] Register `RegistryIndexWorker` in `apps/control-plane/entrypoints/worker_main.py` lifespan — start on startup, graceful stop on shutdown
- [x] T031 [P] Call `registry_opensearch_setup.create_marketplace_agents_index()` and `registry_qdrant_setup.create_agent_embeddings_collection()` in both `apps/control-plane/entrypoints/api_main.py` and `apps/control-plane/entrypoints/worker_main.py` lifespan startup hooks (idempotent — safe to call on every restart)
- [x] T032 [P] Write unit tests in `apps/control-plane/tests/unit/test_registry_package_validator.py` — path traversal rejected, symlink rejected, size limit rejected, valid package accepted, manifest missing required fields rejected, both YAML and JSON manifests parsed, custom role without description rejected
- [x] T033 [P] Write unit tests in `apps/control-plane/tests/unit/test_registry_state_machine.py` — every valid transition allowed, every invalid transition rejected, `get_valid_transitions()` returns correct sets for each status, `archived` has empty valid transitions
- [x] T034 [P] Write unit tests in `apps/control-plane/tests/unit/test_registry_schemas.py` — `AgentManifest` validation (required fields, slug regex, semver, custom role validator), `AgentDiscoveryParams` defaults, `AgentPatch` partial update model
- [x] T035 [P] Write unit tests in `apps/control-plane/tests/unit/test_registry_visibility_filter.py` — FQN pattern matching via `re.fullmatch()`, union of agent patterns + workspace grants, wildcard `*` matches all, empty list matches nothing, invalid regex raises error
- [x] T036 Write integration tests in `apps/control-plane/tests/integration/test_registry_upload.py` — full upload flow: valid package → 201 + profile + revision; second version → 200 + `created=false`; path traversal → 422; symlink → 422; size limit → 422; missing purpose → 422; MinIO upload confirmed; OpenSearch document created; no data on failure
- [x] T037 [P] Write integration tests in `apps/control-plane/tests/integration/test_registry_discovery.py` — FQN resolution within 200ms, FQN pattern matching, keyword search, visibility filtering (zero visibility = 0 results, pattern = filtered results)
- [x] T038 [P] Write integration tests in `apps/control-plane/tests/integration/test_registry_lifecycle.py` — all valid transitions succeed + audit records created + Kafka events emitted; all invalid transitions return 409; archived agent not in discovery
- [x] T039 [P] Write integration tests in `apps/control-plane/tests/integration/test_registry_visibility.py` — per-agent patterns, workspace grants union, wildcard `["*"]`, PATCH visibility takes effect immediately on next query, invalid pattern rejected at PATCH time
- [x] T040 [P] Write integration tests in `apps/control-plane/tests/integration/test_registry_revisions.py` — PATCH does not create revision, upload new version creates revision, list revisions in chronological order, revision content immutable
- [x] T041 Run ruff check and mypy --strict on `apps/control-plane/src/platform/registry/` — resolve all lint and type errors; verify test coverage ≥ 95%

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories; T005/T006/T007 parallelizable after T001
- **US1 (Phase 3)**: Depends on Phase 2 — T008/T009 parallelizable; T010 needs T008; T011 needs T010; T012 parallelizable with T009
- **US2 (Phase 4)**: Depends on Phase 3 complete (needs models, repository, service base)
- **US3 (Phase 5)**: Depends on Phase 3 complete (needs models, service, events base)
- **US4 (Phase 6)**: Depends on Phase 3 complete
- **US5 (Phase 7)**: Depends on Phase 3 complete; US2 must be complete (visibility applies in list_agents)
- **US6 (Phase 8)**: Depends on Phase 3 complete
- **Polish (Phase 9)**: Depends on all desired user stories complete; T032–T040 parallelizable

### User Story Dependencies

- **US1 (P1)**: Foundation required — no other story dependency
- **US2 (P1)**: US1 required (needs agent profiles to discover)
- **US3 (P1)**: US1 required (needs agents to transition); US2 recommended (visibility filters discovery post-transition)
- **US4 (P2)**: US1 required; US2 recommended (maturity filter in discovery)
- **US5 (P2)**: US1 + US2 required (visibility affects discovery query)
- **US6 (P3)**: US1 required; builds on PATCH endpoint started in US5

### Within Each User Story

- Models and schemas in parallel before service
- Service before router (DI wiring)
- Repository additions before service additions using them

### Parallel Opportunities

- T005, T006, T007 — all foundational modules, different files
- T008, T009, T012 — models, schemas, event stubs — different files
- T019 — event additions independent of service work
- T025 — repository immutability check independent of T026
- T028, T030, T031 — background task wiring all independent
- T032–T040 — all test files independent of each other

---

## Parallel Example: Phase 3 (US1)

```
# Launch in parallel after T007 completes:
Task T008: Implement models.py (AgentNamespace, AgentProfile, AgentRevision, AgentMaturityRecord, LifecycleAuditEntry)
Task T009: Implement schemas.py (AgentManifest + all request/response schemas)
Task T012: Start events.py stub (AgentCreatedPayload)

# Then sequentially:
Task T010: repository.py (depends on T008 models)
Task T011: service.py (depends on T009 schemas + T010 repository)
Task T013: dependencies.py (depends on T011 service)
Task T014: router.py (depends on T013 dependencies)
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 — all P1)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational)
2. Complete Phase 3 (US1 — registration)
3. Complete Phase 4 (US2 — discovery)
4. Complete Phase 5 (US3 — lifecycle)
5. **STOP and VALIDATE**: Run quickstart.md scenarios 1–3 end-to-end
6. All three P1 stories together form the deployable MVP

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 → namespace management + package upload → uploadable agents
3. US2 → FQN resolution + discovery → discoverable agents (MVP!)
4. US3 → lifecycle transitions + audit → governable agents
5. US4 → maturity classification → trustworthy agents
6. US5 → visibility management → secure agents
7. US6 → metadata updates + revision history → developer-friendly agents

### Parallel Team Strategy

With multiple developers after Phase 2 completes:
- Developer A: US1 (registration + upload pipeline) — critical path
- Developer B: US3 (state machine + lifecycle) — can build independently
- Developer C: US4 + US6 (maturity + revision history) — can build independently
- US2 and US5 depend on US1 completion — assign after US1 ships

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks in current phase
- Each user story is independently testable via its **Independent Test** scenario
- `package_validator.py` (T007) is the security-critical component — test exhaustively in T032
- Revision immutability (T025) must be enforced at the repository layer, not just the service layer
- Embedding generation (T028) is async/eventually-consistent — integration tests should poll `embedding_status` rather than checking immediately
- `registry_opensearch_setup.py` and `registry_qdrant_setup.py` use the same idempotent pattern as `clickhouse_setup.py` from feature 020
- The `GET /api/v1/agents/resolve/{fqn}` route must be registered BEFORE `GET /api/v1/agents/{agent_id}` in FastAPI to avoid route shadowing — `resolve` is a literal path segment not a UUID
