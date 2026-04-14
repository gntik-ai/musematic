# Tasks: OpenSearch Full-Text Search

**Input**: Design documents from `specs/008-opensearch-full-text-search/`  
**Branch**: `008-opensearch-full-text-search`  
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Organization**: Tasks are grouped by user story (8 stories: US1–US3 P1, US4–US8 P2) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Exact file paths included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Directories, dependency declarations, and chart skeleton before any story work begins.

- [X] T001 Create Helm chart skeleton at `deploy/helm/opensearch/` with `Chart.yaml` declaring dependencies on `opensearch-project/opensearch` (v2.18.x) and `opensearch-project/opensearch-dashboards` (v2.18.x) and add the opensearch Helm repo to repo documentation
- [X] T002 Create `deploy/opensearch/init/` directory with empty `init_opensearch.py` and `requirements.txt` (opensearch-py==2.x) for the init Job Python script
- [X] T003 Add `opensearch-py>=2.0` to `apps/control-plane/pyproject.toml` under `[project.dependencies]`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared Kubernetes resources and Python dependency that ALL user stories depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Create Kubernetes Secret template `deploy/helm/opensearch/templates/secret-credentials.yaml` with `OPENSEARCH_USERNAME` and `OPENSEARCH_PASSWORD` keys, rendered from Helm values; include `secretKeyRef` references for use in the StatefulSet env
- [X] T005 [P] Create ConfigMap template `deploy/helm/opensearch/templates/configmap-synonyms.yaml` containing `agent-synonyms.txt` with the three initial synonym groups from data-model.md (summarizer, translator, classifier) — mounted at `/usr/share/opensearch/config/synonyms/agent-synonyms.txt`
- [X] T006 [P] Add Pydantic `Settings` fields for OpenSearch to `apps/control-plane/src/platform/common/config.py`: `OPENSEARCH_HOSTS`, `OPENSEARCH_USERNAME`, `OPENSEARCH_PASSWORD`, `OPENSEARCH_USE_SSL`, `OPENSEARCH_VERIFY_CERTS`, `OPENSEARCH_TIMEOUT`

**Checkpoint**: Foundation ready — Helm templates, Secret, ConfigMap, and config fields exist. User story phases can begin.

---

## Phase 3: User Story 1 — Deploy Search Engine Cluster (Priority: P1) 🎯 MVP

**Goal**: A running OpenSearch cluster (1 node dev, 3 nodes prod) with OpenSearch Dashboards, ICU plugin, and synonym ConfigMap mounted — verified by cluster health API.

**Independent Test**: `helm install --dry-run` succeeds; after real install, `GET /_cluster/health` returns `yellow` (dev single-node) or `green` (prod 3-node); Dashboards pod is Running; analyzer test shows synonym expansion tokens.

- [X] T007 [US1] Create `deploy/helm/opensearch/values.yaml` with shared defaults: ICU analysis-icu init container (using same OpenSearch image, runs `opensearch-plugin install --batch analysis-icu`), synonym ConfigMap volume mount, Dashboards enabled, persistence 10Gi, resource requests per data-model.md §4.1, `DISABLE_SECURITY_PLUGIN: "false"` default
- [X] T008 [P] [US1] Create `deploy/helm/opensearch/values-prod.yaml` with production overrides: `replicas: 3`, JVM heap `8g`, persistence `100Gi` storageClass `fast`, Dashboards pointing to HTTPS endpoint per data-model.md §4.2
- [X] T009 [P] [US1] Create `deploy/helm/opensearch/values-dev.yaml` with dev overrides: `replicas: 1`, JVM heap `512m`, `DISABLE_SECURITY_PLUGIN: "true"`, `discovery.type: single-node`, `DISABLE_SECURITY_DASHBOARDS_PLUGIN: "true"` per data-model.md §4.3
- [X] T010 [US1] Create NetworkPolicy template `deploy/helm/opensearch/templates/network-policy.yaml`: allow ingress on `9200/TCP` from `platform-control` and `platform-execution` namespaces, `9600/TCP` from `platform-observability`, `9200/TCP` within `platform-data` (for Dashboards); deny all other ingress per contracts/opensearch-cluster.md §7
- [X] T011 [US1] Validate the wrapper chart renders correctly: run `helm dependency update deploy/helm/opensearch` then `helm template musematic-opensearch deploy/helm/opensearch -f deploy/helm/opensearch/values-dev.yaml` and confirm StatefulSet, Dashboards Deployment, Secret, ConfigMap, NetworkPolicy, and future Job all render without errors
- [X] T012 [US1] Integration test in `apps/control-plane/tests/integration/test_opensearch_cluster.py`: deploy OpenSearch testcontainer (single-node, security disabled), call `GET /_cluster/health` via opensearch-py, assert `status == "yellow"` and `number_of_nodes == 1`; call `GET /_analyze` with `agent_analyzer` after template init, assert synonym tokens present

**Checkpoint**: Running cluster with green/yellow health, Dashboards accessible, ICU analyzer functional. US1 independently testable.

---

## Phase 4: User Story 2 — Initialize Index Templates and Mappings (Priority: P1)

**Goal**: All three index templates (`marketplace-agents`, `audit-events`, `connector-payloads`), two ISM policies, snapshot repository, and SM snapshot policy created by an idempotent Python init Job.

**Independent Test**: Run `init_opensearch.py` twice against a running cluster; verify all templates exist via `GET /_index_template`; verify ISM policies via `GET /_plugins/_ism/policies`; confirm second run produces no errors and no duplicates.

- [X] T013 [US2] Implement ISM policy creation in `deploy/opensearch/init/init_opensearch.py`: `create_ism_policies()` function using `opensearch-py` `AsyncOpenSearch` — PUT `_plugins/_ism/policies/audit-events-policy` and `_plugins/_ism/policies/connector-payloads-policy` with retention config from data-model.md §2; use `if_seq_no`/`if_primary_term` pattern or unconditional PUT for idempotency
- [X] T014 [P] [US2] Implement index template creation in `deploy/opensearch/init/init_opensearch.py`: `create_index_templates()` function — PUT `_index_template/marketplace-agents` with `agent_analyzer` (synonym_filter + icu_folding + lowercase), PUT `_index_template/audit-events`, PUT `_index_template/connector-payloads` with all field mappings from data-model.md §1; create initial alias indexes (`marketplace-agents-000001`, `audit-events-000001`, `connector-payloads-000001`)
- [X] T015 [P] [US2] Implement snapshot repository registration and SM policy in `deploy/opensearch/init/init_opensearch.py`: `setup_snapshot_management()` — PUT `_snapshot/opensearch-backups` (S3 type, MinIO endpoint, bucket `musematic-backups`, base path `backups/opensearch/`) and PUT `_plugins/_sm/policies/daily-snapshot` (cron `0 5 * * *`, retain 30 snapshots / 30 days) per data-model.md §3
- [X] T016 [US2] Create Helm post-install/post-upgrade Job template `deploy/helm/opensearch/templates/init-job.yaml`: Python 3.12-slim image, runs `python init_opensearch.py`, mounts init script ConfigMap, env vars from `opensearch-credentials` Secret and `initJob.*` Helm values; `restartPolicy: OnFailure`, `helm.sh/hook: post-install,post-upgrade`
- [X] T017 [US2] Integration test in `apps/control-plane/tests/integration/test_opensearch_init.py`: spin up OpenSearch testcontainer, run `init_opensearch.py` functions directly, assert `marketplace-agents` template has `agent_analyzer` in settings, `audit-events` template references `audit-events-policy`, `connector-payloads` template references `connector-payloads-policy`; run init a second time and assert no errors (idempotency test)

**Checkpoint**: Three index templates and two ISM policies exist. Init is idempotent. US2 independently testable.

---

## Phase 5: User Story 3 — Services Index and Search Marketplace Agents (Priority: P1)

**Goal**: `AsyncOpenSearchClient` wrapper and `AgentSearchProjection` that enables BM25 search with synonym expansion, workspace-scoped filters, and faceted aggregations over indexed agent profiles.

**Independent Test**: Index 50 agent profiles across 3 workspaces; search for "summarizer" — verify "text summary agent" appears in top 10; apply workspace filter — verify zero cross-workspace results; request aggregations — verify correct counts per capability and maturity level.

- [X] T018 [US3] Implement `AsyncOpenSearchClient` class skeleton in `apps/control-plane/src/platform/common/clients/opensearch.py`: constructor accepting `hosts`, `http_auth`, `use_ssl`, `verify_certs`, `ca_certs`, `timeout` — instantiates `AsyncOpenSearch` from `opensearch_py`; implement `close()` and `health_check()` returning `ClusterHealth` dataclass per contracts/python-opensearch-client.md §3
- [X] T019 [P] [US3] Implement `SearchResult`, `BulkIndexResult`, `ClusterHealth` dataclasses and `OpenSearchClientError`, `OpenSearchConnectionError`, `OpenSearchIndexError`, `OpenSearchQueryError` exception classes in `apps/control-plane/src/platform/common/clients/opensearch.py` per contracts/python-opensearch-client.md §4–§5
- [X] T020 [US3] Implement `index_document` and `bulk_index` methods in `apps/control-plane/src/platform/common/clients/opensearch.py`: `index_document` calls `client.index()`, returns document ID; `bulk_index` uses `helpers.async_bulk`, captures per-document errors in `BulkIndexResult.errors` without raising on partial failure per contracts/python-opensearch-client.md §3.1–§3.2
- [X] T021 [US3] Implement `search` and `search_after` methods in `apps/control-plane/src/platform/common/clients/opensearch.py`: both inject `workspace_id` as mandatory `bool.filter` term wrapping the caller's query (per contracts §6 workspace isolation guarantee); `search` caps `size` at 10000; `search_after` returns cursor in `SearchResult.search_after`; implement `delete_document` and `delete_by_query` per contracts §3.3–§3.6
- [X] T022 [P] [US3] Implement `AgentSearchProjection` in `apps/control-plane/src/platform/search/projections.py`: `index_agent(agent_profile)`, `delete_agent(agent_id, workspace_id)`, `bulk_reindex(agents)` methods using `AsyncOpenSearchClient`; implement `build_agent_query(query_text, workspace_id, capabilities, maturity_level, lifecycle_state, certification_status)` and `build_agent_aggregations()` helpers returning OpenSearch DSL dicts per data-model.md §8.1
- [X] T023 [US3] Wire `AsyncOpenSearchClient` into FastAPI lifespan in `apps/control-plane/src/platform/main.py`: instantiate on startup from `config.OPENSEARCH_*` settings, store as `app.state.opensearch_client`, close on shutdown; add `get_opensearch_client()` to `apps/control-plane/src/platform/common/dependencies.py`
- [X] T024 [US3] Integration test in `apps/control-plane/tests/integration/test_opensearch_search.py`: use testcontainers OpenSearch + init templates; index 50 agent documents across 3 workspaces with varied capabilities/maturity; assert BM25 search returns results ranked by relevance; assert `search_after` cursor pagination retrieves all documents; assert workspace filter returns zero cross-workspace hits (SC-006)
- [X] T025 [US3] Integration test in `apps/control-plane/tests/integration/test_opensearch_synonyms.py`: after template init, index one agent with `name="Text Summary Agent"` in workspace `ws-1`; search for `"summarizer"` using `agent_analyzer`; assert the agent appears in results (synonym expansion via `agent-synonyms.txt`); assert faceted aggregation returns correct capability counts (SC-003, SC-005)

**Checkpoint**: Marketplace search fully functional — BM25, synonyms, workspace isolation, faceted aggregations all pass. US3 independently testable.

---

## Phase 6: User Story 4 — Services Index and Search Audit Events (Priority: P2)

**Goal**: `AuditSearchProjection` enabling audit event indexing and search by event type, time range, actor, and workspace — using the pre-existing `audit-events-*` index template.

**Independent Test**: Index 1000 audit events across 5 workspaces; search by event_type + time range — verify only matching events returned in chronological order; search with workspace filter — verify zero cross-workspace results.

- [X] T026 [US4] Implement `AuditSearchProjection` in `apps/control-plane/src/platform/search/projections.py`: `index_event(event: AuditEvent)` maps audit event fields to `audit-events-000001` document (event_id, event_type, actor_id, actor_type, timestamp, workspace_id, resource_type, action, details, indexed_at); uses `AsyncOpenSearchClient.index_document()`
- [X] T027 [P] [US4] Add `build_audit_query(event_type, workspace_id, time_from, time_to, free_text)` helper in `apps/control-plane/src/platform/search/projections.py`: builds `bool.filter` with `term` filters and `range` on timestamp, plus optional `match` on `details` field; sort by timestamp descending per data-model.md §8.2
- [X] T028 [US4] Integration test in `apps/control-plane/tests/integration/test_opensearch_audit.py`: index 1000 audit events across 5 workspaces and 10 event types; search by `event_type=AGENT_REVOKED` + time range — assert only matching events returned in descending timestamp order; search with free-text details query — assert relevance ranking; assert workspace filter returns zero cross-workspace hits

**Checkpoint**: Audit search works independently of marketplace search. US4 testable without US3.

---

## Phase 7: User Story 5 — ISM Auto-manages Data Retention (Priority: P2)

**Goal**: Verify that ISM policies created in US2 correctly expire audit-events and connector-payloads indexes while marketplace-agents indexes are retained indefinitely.

**Independent Test**: Create an index with a 1-minute ISM policy; wait for deletion; verify the index no longer exists. Verify marketplace-agents index has no ISM policy attached.

- [X] T029 [US5] Integration test in `apps/control-plane/tests/integration/test_opensearch_ism.py`: create a test index `audit-events-ism-test` with a short-retention ISM policy (min_index_age: 1m, transitions to delete); poll `GET /_plugins/_ism/explain` until policy state is `delete`; assert the index is deleted (SC-007)
- [X] T030 [P] [US5] Integration test in `apps/control-plane/tests/integration/test_opensearch_ism.py`: verify `marketplace-agents-000001` has no ISM policy attached (`GET /_plugins/_ism/explain/marketplace-agents-000001` returns `policy_id: null`); assert connector-payloads template has `connector-payloads-policy` configured (30-day retention per spec US5)

**Checkpoint**: ISM auto-deletion confirmed for audit and connector indexes; marketplace index confirmed policy-free.

---

## Phase 8: User Story 6 — Operator Backs Up and Restores Search Indexes (Priority: P2)

**Goal**: Verify snapshot repository (registered at init time), trigger a manual snapshot, confirm it completes, delete an index, restore from snapshot, and verify all documents are recovered.

**Independent Test**: Trigger snapshot, verify `state == SUCCESS` within 15 minutes; delete index; restore; assert document count matches original.

- [X] T031 [US6] Integration test in `apps/control-plane/tests/integration/test_opensearch_snapshot.py`: verify snapshot repository `opensearch-backups` exists (`GET /_snapshot/opensearch-backups`); trigger manual snapshot `PUT /_snapshot/opensearch-backups/manual-test-1`; poll until `state == SUCCESS` (timeout 15 minutes); assert snapshot stored (SC-008)
- [X] T032 [US6] Integration test in `apps/control-plane/tests/integration/test_opensearch_snapshot.py`: index 100 documents in `marketplace-agents-000001`; take snapshot; delete the index (`DELETE /marketplace-agents-000001`); restore from snapshot (`POST /_snapshot/opensearch-backups/manual-test-1/_restore`); verify restored index has 100 documents with zero document loss (SC-009)
- [X] T033 [P] [US6] Verify SM policy in `apps/control-plane/tests/integration/test_opensearch_snapshot.py`: call `GET /_plugins/_sm/policies/daily-snapshot`; assert `creation.schedule.cron.expression == "0 5 * * *"` and `deletion.delete_condition.max_count == 30`

**Checkpoint**: Snapshot backup and restore fully verified. US6 independently testable.

---

## Phase 9: User Story 7 — Network Access Restricted to Authorized Namespaces (Priority: P2)

**Goal**: Confirm the NetworkPolicy template (created in US1) correctly allows authorized namespace access and blocks unauthorized namespaces.

**Independent Test**: Helm template renders NetworkPolicy with correct `namespaceSelector` entries; manual validation: connection from `platform-control` succeeds, connection from `default` namespace fails.

- [X] T034 [US7] Validate NetworkPolicy template in `deploy/helm/opensearch/templates/network-policy.yaml`: render with `helm template` and assert the rendered YAML contains `ingress` rules for `platform-control` (port 9200), `platform-execution` (port 9200), `platform-observability` (port 9600), and `platform-data` (same namespace, port 9200 for Dashboards); assert no `ingress` rule exists for `default` namespace or wildcard (per contracts/opensearch-cluster.md §7)

**Checkpoint**: NetworkPolicy template verified. US7 complete.

---

## Phase 10: User Story 8 — Synonym Dictionary Extensible by Administrators (Priority: P2)

**Goal**: Verify that an administrator can add a new synonym to the ConfigMap, trigger analyzer reload via index close/open, and have new searches use the updated synonyms.

**Independent Test**: Add synonym `"compressor" → "data compression agent"`; reload index analyzers; search for "compressor" — agent described as "data compression agent" appears in results.

- [X] T035 [US8] Integration test in `apps/control-plane/tests/integration/test_opensearch_synonyms.py`: index one agent with `description="data compression agent"`; confirm searching "compressor" returns zero results (synonym not yet configured); update synonym filter to add `compressor, data compression agent`; call `POST /marketplace-agents-000001/_close` then `POST /marketplace-agents-000001/_open` (or `POST /_reload_search_analyzers`); search for "compressor" again — assert agent appears in results (SC-003 extensibility)
- [X] T036 [P] [US8] Document synonym update runbook in `specs/008-opensearch-full-text-search/quickstart.md` §14: confirm existing steps cover (1) `kubectl edit configmap opensearch-synonyms`, (2) index close/open procedure, (3) `_analyze` verification — update section if any step is missing or incorrect based on integration test findings

**Checkpoint**: Synonym extensibility confirmed end-to-end. All 8 user stories complete.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Health integration, observability wiring, and final validation across all stories.

- [X] T037 [P] Add OpenSearch health check to platform diagnostic tooling: implement `check_opensearch()` in `apps/control-plane/src/platform/common/clients/opensearch.py` calling `health_check()` and returning a structured result for `platform-cli diagnose` — per user's plan item 9
- [X] T038 [P] Verify `OPENSEARCH_*` environment variables are documented in the Helm chart's `values.yaml` comments and in `deploy/helm/opensearch/templates/init-job.yaml` env mapping; ensure Secret reference is consistent across all templates
- [ ] T039 Run full quickstart.md validation: execute all 15 sections against a dev deployment; verify every `curl` command, analyzer test, facet aggregation, workspace isolation check, and Dashboards access step produces the documented expected output; file corrections in quickstart.md for any discrepancies

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2
- **US2 (Phase 4)**: Depends on US1 (cluster must be running before init Job is tested)
- **US3 (Phase 5)**: Depends on US2 (templates must exist for search tests)
- **US4–US8 (Phases 6–10)**: Depend on US2; US4–US8 are independent of each other and can proceed in parallel after US2
- **Polish (Phase 11)**: Depends on all user stories complete

### User Story Dependencies

- **US1** → **US2** → **US3** (sequential P1 chain — each builds on the previous)
- **US4**, **US5**, **US6**, **US7**, **US8**: all depend on US2 only; fully independent of each other

### Within Each User Story

- Foundation tasks before story-specific tasks
- Helm templates before integration tests
- Client implementation (T018–T021) before projection writers (T022–T023)
- `search` method before aggregation tests

### Parallel Opportunities

- T008, T009 (values-prod, values-dev) run in parallel
- T004, T005, T006 (Secret, ConfigMap, config fields) run in parallel
- T013, T014, T015 (ISM policies, templates, snapshot repo) run in parallel within US2
- T018, T019 (client skeleton + types) run in parallel within US3
- T022 (AgentSearchProjection) runs in parallel with T021 (search methods)
- US4, US5, US6, US7, US8 run in parallel after US2 is complete
- T037, T038 (polish) run in parallel

---

## Parallel Example: User Story 2 (Init Templates)

```
# All three init functions can be implemented in parallel (same file, separate functions):
Task T013: "Implement ISM policy creation in deploy/opensearch/init/init_opensearch.py"
Task T014: "Implement index template creation in deploy/opensearch/init/init_opensearch.py"
Task T015: "Implement snapshot repository + SM policy in deploy/opensearch/init/init_opensearch.py"
# Then T016 (Helm Job) + T017 (integration test) sequentially after
```

## Parallel Example: User Story 3 (Marketplace Search)

```
# Types + client skeleton in parallel:
Task T018: "Implement AsyncOpenSearchClient skeleton in opensearch.py"
Task T019: "Implement SearchResult, BulkIndexResult, ClusterHealth dataclasses in opensearch.py"

# Then methods sequentially (T020 → T021)
# Then in parallel:
Task T022: "Implement AgentSearchProjection in projections.py"
Task T023: "Wire client into FastAPI lifespan in main.py"

# Then integration tests in parallel:
Task T024: "Integration test: search, workspace isolation"
Task T025: "Integration test: synonym expansion, faceted aggregations"
```

## Parallel Example: P2 User Stories (after US2 complete)

```
# All P2 stories can start simultaneously:
Task T026: "AuditSearchProjection — US4"
Task T029: "ISM expiry test — US5"
Task T031: "Snapshot backup test — US6"
Task T034: "NetworkPolicy validation — US7"
Task T035: "Synonym extensibility test — US8"
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T006)
3. Complete Phase 3: US1 — Deploy cluster (T007–T012)
4. Complete Phase 4: US2 — Init templates (T013–T017)
5. Complete Phase 5: US3 — Marketplace search (T018–T025)
6. **STOP and VALIDATE**: Full marketplace search works (BM25, synonyms, workspace isolation, facets)
7. Deploy/demo MVP

### Incremental Delivery

1. Setup + Foundational → infrastructure scaffold
2. US1 → running cluster with Dashboards (**cluster deploy demo**)
3. US2 → all templates and ISM policies active (**index init demo**)
4. US3 → marketplace search operational (**MVP: agent discovery**)
5. US4 → audit search (**compliance search demo**)
6. US5 → ISM verified (**data retention demo**)
7. US6 → backup/restore (**operational resilience demo**)
8. US7 + US8 → security + synonyms (**production hardening**)

### Parallel Team Strategy

With multiple developers, after US2 is complete:
- **Developer A**: US3 (marketplace search — highest priority P1)
- **Developer B**: US4 (audit search) + US5 (ISM)
- **Developer C**: US6 (snapshots) + US7 (network policy) + US8 (synonyms)

---

## Notes

- [P] tasks target different functions or files — safe to parallelize
- Workspace isolation (`workspace_id` filter) is mandatory in every search call — verified in T024
- Security plugin state must be consistent between OpenSearch and Dashboards — dev both disabled, prod both enabled
- ISM is OpenSearch's native lifecycle system (not Elasticsearch ILM) — use `_plugins/_ism/` API endpoints throughout
- Snapshot Management (SM) replaces the Kubernetes CronJob pattern — all snapshot scheduling via `_plugins/_sm/`
- ICU plugin install via init container — verify init container logs if analyzer tests fail
- Synonym updates require index close/open or `_reload_search_analyzers` — documented in quickstart §14
- Commit after each phase checkpoint to keep git history clean
