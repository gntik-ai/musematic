# Tasks: Qdrant Vector Search

**Input**: Design documents from `specs/005-qdrant-vector-search/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory scaffolding and add dependencies before any story work begins.

- [X] T001 Create `deploy/helm/qdrant/` directory and all subdirectories (`templates/`)
- [X] T002 [P] Create `apps/control-plane/scripts/` directory if it does not already exist
- [X] T003 [P] Add `qdrant-client[grpc]>=1.12` to `apps/control-plane/pyproject.toml` under `[project.dependencies]`
- [X] T004 [P] Add `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_GRPC_PORT`, `QDRANT_COLLECTION_DIMENSIONS` settings to `apps/control-plane/src/platform/common/config.py` with defaults (`http://musematic-qdrant.platform-data:6333`, empty string, `6334`, `768`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Exception class and shared data types used by all Qdrant operations.

**⚠️ CRITICAL**: No user story work on the Python client can begin until this phase is complete.

- [X] T005 Add `QdrantError` exception class to `apps/control-plane/src/platform/common/exceptions.py`
- [X] T006 [P] Define `PointStruct`, `ScoredPoint`, `CollectionInfo` frozen dataclasses and `workspace_filter` helper in `apps/control-plane/src/platform/common/clients/qdrant.py` — leave `AsyncQdrantClient` as a stub class; `workspace_filter(workspace_id, extra=None)` returns a `qdrant_client.models.Filter` combining a mandatory `workspace_id` keyword match with any additional conditions from `extra`

**Checkpoint**: Shared types, exception, and `workspace_filter` ready — all user story phases can now begin.

---

## Phase 3: User Story 1 — Platform Operator Deploys Vector Search Cluster (Priority: P1) 🎯 MVP

**Goal**: A production-ready 3-node Qdrant cluster (replication factor 2) or single-node dev deployment, deployable via a single Helm command.

**Independent Test**: `helm install musematic-qdrant deploy/helm/qdrant -n platform-data -f values.yaml -f values-prod.yaml` completes; `kubectl rollout status statefulset/musematic-qdrant -n platform-data` succeeds; `curl http://localhost:6333/cluster -H "Authorization: api-key $KEY"` returns `{"status": "ok", "result": {"peer_count": 3}}`.

- [X] T007 [US1] Create `deploy/helm/qdrant/Chart.yaml` with `apiVersion: v2`, `name: musematic-qdrant`, `version: 0.1.0`, `description: Qdrant vector search for Musematic platform`; add `dependencies` entry for the official Qdrant chart: `name: qdrant`, `repository: https://qdrant.github.io/qdrant-helm`, pinned to an exact version (e.g., `0.8.4`)
- [X] T008 [P] [US1] Create `deploy/helm/qdrant/values.yaml` with shared defaults: `qdrant.replicaCount: 3`, `qdrant.config.cluster.enabled: true`, `qdrant.config.cluster.p2p.port: 6335`, `qdrant.config.storage.hnsw_index.m: 16`, `qdrant.config.storage.hnsw_index.ef_construct: 128`, `qdrant.config.storage.hnsw_index.full_scan_threshold: 10000`, `qdrant.persistence.storageClassName: standard`, `qdrant.persistence.size: 50Gi`, `qdrant.resources.requests.memory: 2Gi`, `collections.dimensions: 768`, `collections.replicationFactor: 2`, `networkPolicy.enabled: true`, `backup.enabled: true`, `backup.schedule: "0 2 * * *"`, `backup.bucket: backups`, `backup.prefix: qdrant`
- [X] T009 [P] [US1] Create `deploy/helm/qdrant/values-prod.yaml` with production overrides: `qdrant.replicaCount: 3`, `qdrant.persistence.size: 100Gi`, `qdrant.resources.requests.memory: 4Gi`, `qdrant.resources.requests.cpu: "2"`, `collections.replicationFactor: 2`, `networkPolicy.enabled: true`
- [X] T010 [P] [US1] Create `deploy/helm/qdrant/values-dev.yaml` with development overrides: `qdrant.replicaCount: 1`, `qdrant.config.cluster.enabled: false`, `qdrant.persistence.size: 10Gi`, `qdrant.resources.requests.memory: 512Mi`, `collections.replicationFactor: 1`, `networkPolicy.enabled: false`, `backup.enabled: false`
- [X] T011 [US1] Create `deploy/helm/qdrant/templates/secret-api-key.yaml` — `Secret` named `qdrant-api-key` with `QDRANT_API_KEY` key; use Helm `lookup` to avoid regenerating the key on upgrades: `{{ (lookup "v1" "Secret" .Release.Namespace "qdrant-api-key").data.QDRANT_API_KEY | default (randAlphaNum 32 | b64enc) }}`; mount the secret in the StatefulSet by passing it as `qdrant.env.QDRANT__SERVICE__API_KEY` in values

**Checkpoint**: `helm lint deploy/helm/qdrant` passes; `helm template ... -f values-prod.yaml | grep "kind: StatefulSet"` shows 3 replicas; `helm template ... -f values-dev.yaml | grep "kind: StatefulSet"` shows 1 replica.

---

## Phase 4: User Story 2 — Platform Creates All Required Collections (Priority: P1)

**Goal**: All 4 collections (`agent_embeddings`, `memory_embeddings`, `pattern_embeddings`, `test_similarity`) exist with correct HNSW configuration and payload indexes after running the init script.

**Independent Test**: Run `init_qdrant_collections.py`; verify all 4 collections exist via `GET /collections`; verify each has `vectors_count: 0`, `status: green`, and configured dimension; verify payload indexes exist for each collection.

- [X] T012 [US2] Create `apps/control-plane/scripts/init_qdrant_collections.py` — idempotent script using `AsyncQdrantClient.create_collection_if_not_exists()` for each of the 4 collections with: `vector_size` from `QDRANT_COLLECTION_DIMENSIONS` env var (default 768), `distance: Cosine`, `hnsw_config: HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10000)`, `replication_factor` from `QDRANT_REPLICATION_FACTOR` env var (default 2); then calls `create_payload_index()` for each indexed field per the data-model.md payload index tables; prints a summary of created vs. already-existing collections; exits with code 0 on success

**Checkpoint**: Running `python3 apps/control-plane/scripts/init_qdrant_collections.py` twice produces the same result — second run reports "already exists" for all collections.

---

## Phase 5: User Story 3 — Services Upsert and Search Vectors with Payload Filtering (Priority: P1)

**Goal**: Python services can upsert embedding vectors with payloads, search with mandatory `workspace_id` filters, and receive ranked results with full payloads.

**Independent Test**: Upsert 100 vectors across 3 workspaces; search with a `workspace_id` filter; verify all results belong to the target workspace, are sorted by descending score, and include payloads.

- [X] T013 [US3] Implement `AsyncQdrantClient.__init__` in `apps/control-plane/src/platform/common/clients/qdrant.py` using `qdrant_client.AsyncQdrantClient(url, api_key, prefer_grpc=True, grpc_port)` — constructor reads `settings.QDRANT_URL`, `settings.QDRANT_API_KEY`, `settings.QDRANT_GRPC_PORT`; wraps underlying client in `self._client`
- [X] T014 [US3] Implement `upsert_vectors(collection, points, wait=True)` in `apps/control-plane/src/platform/common/clients/qdrant.py` — calls `self._client.upsert(collection_name=collection, points=[...], wait=wait)`; converts `PointStruct` to `qdrant_client.models.PointStruct`; wraps exceptions in `QdrantError`
- [X] T015 [US3] Implement `search_vectors(collection, query_vector, filter, limit, with_payload, score_threshold)` in `apps/control-plane/src/platform/common/clients/qdrant.py` — calls `self._client.search(collection_name, query_vector, query_filter=filter, limit=limit, with_payload=with_payload, score_threshold=score_threshold)`; maps results to `list[ScoredPoint]`; wraps exceptions in `QdrantError`
- [X] T016 [US3] Implement `delete_vectors(collection, point_ids)` in `apps/control-plane/src/platform/common/clients/qdrant.py` — calls `self._client.delete(collection_name, points_selector=PointIdsList(points=point_ids))`; wraps exceptions in `QdrantError`
- [X] T017 [US3] Implement `get_collection_info(collection)` and `health_check()` in `apps/control-plane/src/platform/common/clients/qdrant.py` — `get_collection_info` calls `self._client.get_collection(collection)` and maps to `CollectionInfo`; `health_check` calls `GET /healthz` via REST and returns `{"status": "ok", "collections": [...]}` or `{"status": "error", "error": msg}`
- [X] T018 [US3] Write integration test `apps/control-plane/tests/integration/test_qdrant_basic.py` using testcontainers Qdrant container (or `QDRANT_TEST_MODE` env var): (1) upsert 100 vectors across 3 workspaces with random embeddings; (2) search with `workspace_filter("ws-A")` → assert all results have `workspace_id == "ws-A"`; (3) search with same vector as upserted → assert top result has `score > 0.9999`; (4) delete a vector → `search_vectors` no longer returns it; (5) upsert with wrong dimension → `QdrantError` raised

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_qdrant_basic.py -v` passes all 5 test cases.

---

## Phase 6: User Story 4 — Vector Search Responds Within Latency SLA (Priority: P1)

**Goal**: Search queries against 1M-vector collections with payload filter complete under 50ms at p99; recall ≥ 95% at HNSW defaults.

**Independent Test**: Load 1M random vectors; run 1000 filtered search queries; measure p99 latency; verify < 50ms; compute recall vs. brute-force; verify ≥ 95%.

- [X] T019 [US4] Write integration test `apps/control-plane/tests/integration/test_qdrant_filtered_search.py`: (1) upsert 1000 vectors across 10 workspaces with compound payloads (`workspace_id`, `lifecycle_state`, `maturity_level`); (2) search with compound filter (`workspace_id` AND `lifecycle_state="published"`) → assert all results match both conditions; (3) search with `score_threshold=0.5` → assert all returned scores are ≥ 0.5; (4) brute-force recall test: upsert 100 known vectors, search each, assert top-1 recall = 100% for small collections (brute-force mode below `full_scan_threshold=10000`)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_qdrant_filtered_search.py -v` passes all 4 test cases.

---

## Phase 7: User Story 5 — Operator Backs Up and Restores Vector Data (Priority: P2)

**Goal**: Daily automated snapshots of all 4 collections upload to object storage; restore from snapshot recovers all data.

**Independent Test**: Run `backup_qdrant_snapshots.py`; verify snapshot files appear in `backups/qdrant/` in object storage; delete a collection; restore from snapshot; verify vectors recovered.

- [X] T020 [US5] Create `apps/control-plane/scripts/backup_qdrant_snapshots.py` — async script that: (1) lists all collections via `GET /collections`; (2) for each collection, triggers snapshot via `POST /collections/{name}/snapshots` and waits for completion; (3) downloads the snapshot file from `GET /collections/{name}/snapshots/{snapshot_name}`; (4) uploads to `s3://{BACKUP_BUCKET}/qdrant/{collection}/{timestamp}_{snapshot_name}` via `AsyncObjectStorageClient`; (5) deletes the local snapshot from Qdrant after successful upload (optional, saves disk space); (6) logs per-collection status; exits with code 0 on full success
- [X] T021 [P] [US5] Create `deploy/helm/qdrant/templates/backup-cronjob.yaml` — `CronJob` with `schedule: {{ .Values.backup.schedule }}` (default `"0 2 * * *"`), wrapped in `{{- if .Values.backup.enabled }}`; runs `python3 /app/scripts/backup_qdrant_snapshots.py` using the control-plane container image; mounts `QDRANT_URL`, `QDRANT_API_KEY` from `qdrant-api-key` secret and `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` from `minio-platform-credentials` secret; `restartPolicy: OnFailure`

**Checkpoint**: `python3 apps/control-plane/scripts/backup_qdrant_snapshots.py` runs and produces snapshot files in object storage; `mc ls local/backups/qdrant/` lists the uploaded snapshots.

---

## Phase 8: User Story 6 — Network Access Is Restricted to Authorized Namespaces (Priority: P2)

**Goal**: gRPC (6334) and REST (6333) accessible from `platform-control` and `platform-execution`; metrics (6333) accessible from `platform-observability`; inter-node (6335) accessible within `platform-data`; all other namespaces blocked.

**Independent Test**: Deploy with `networkPolicy.enabled: true`; `kubectl run` pod in `platform-control` → `curl /health` succeeds; `kubectl run` pod in `default` → connection times out.

- [X] T022 [US6] Create `deploy/helm/qdrant/templates/network-policy.yaml` — one `NetworkPolicy` resource wrapped in `{{- if .Values.networkPolicy.enabled }}`: `podSelector: {app.kubernetes.io/name: qdrant}`; four ingress rules: (1) ports 6333+6334 from `platform-control` namespaceSelector; (2) ports 6333+6334 from `platform-execution` namespaceSelector; (3) port 6333 from `platform-observability` namespaceSelector (metrics only); (4) port 6335 from same `podSelector` within `platform-data` (inter-node cluster communication)

**Checkpoint**: `helm template deploy/helm/qdrant -f values.yaml -f values-prod.yaml | grep "kind: NetworkPolicy" | wc -l` outputs 1; `helm template ... -f values-dev.yaml | grep "kind: NetworkPolicy"` outputs nothing.

---

## Phase 9: User Story 7 — All API Requests Require Authentication (Priority: P2)

**Goal**: All REST and gRPC requests require a valid API key; requests without or with invalid keys are rejected with 403.

**Independent Test**: Send a REST request with valid API key → 200; send without API key → 401/403; send with wrong key → 401/403.

- [X] T023 [US7] Verify `deploy/helm/qdrant/templates/secret-api-key.yaml` (created in T011) correctly passes the API key to Qdrant via the `QDRANT__SERVICE__API_KEY` environment variable; add a comment in `values.yaml` explaining the env var name convention (`QDRANT__` prefix maps to nested config keys in Qdrant); write a brief authentication verification note in `quickstart.md` section "Verify Authentication" showing the rejected-request test commands

**Checkpoint**: After deployment, `curl http://localhost:6333/collections` without auth header returns HTTP 401; `curl ... -H "Authorization: api-key <key>"` returns HTTP 200.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, linting, type checking, Helm lint.

- [X] T024 [P] Implement `create_collection_if_not_exists` and `create_payload_index` methods in `apps/control-plane/src/platform/common/clients/qdrant.py` (stub from T006 → full implementation): `create_collection_if_not_exists` calls `self._client.get_collection(name)` — if `CollectionNotExistsException`, calls `self._client.create_collection(...)` with the provided `VectorsConfig` and `HnswConfigDiff`; returns `True` if created, `False` if already existed; `create_payload_index` calls `self._client.create_payload_index(collection_name, field_name, field_schema=field_type)`
- [ ] T025 [P] Run `helm lint deploy/helm/qdrant` and fix any linting errors; run `helm dependency update deploy/helm/qdrant` to download the pinned Qdrant chart version and commit `Chart.lock`; verify `helm template` renders valid YAML for both prod and dev values
- [X] T026 [P] Run `ruff check apps/control-plane/src/platform/common/clients/qdrant.py apps/control-plane/scripts/init_qdrant_collections.py apps/control-plane/scripts/backup_qdrant_snapshots.py` and fix violations
- [X] T027 [P] Run `mypy apps/control-plane/src/platform/common/clients/qdrant.py` in strict mode and fix type errors; add `# type: ignore[import-untyped]` with comment for any missing `qdrant-client` stubs

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks all Python client work**
- **US1 (Phase 3)**: Depends on Phase 1 — Helm only, no Python dependency
- **US2 (Phase 4)**: Depends on US1 (needs running cluster) and Foundational (uses `AsyncQdrantClient`)
- **US3 (Phase 5)**: Depends on Foundational (types) and US2 (collections must exist)
- **US4 (Phase 6)**: Depends on US3 (filtered search requires working `search_vectors`)
- **US5 (Phase 7)**: Depends on US1 (cluster for snapshots), US3 (client), feature 004 (object storage)
- **US6 (Phase 8)**: Depends on US1 (network policy is part of cluster chart)
- **US7 (Phase 9)**: Depends on T011 (API key secret, created in US1)
- **Polish (Phase 10)**: Depends on all phases complete

### Dependency Graph

```
Phase 1 (Setup)
    ├── Phase 2 (Foundational: QdrantError + data types)
    │       └── Phase 3 (US1: Cluster)
    │               └── Phase 4 (US2: Collections init)
    │                       └── Phase 5 (US3: Upsert/Search)
    │                               └── Phase 6 (US4: Latency SLA)
    │               ├── Phase 7 (US5: Backup CronJob)
    │               ├── Phase 8 (US6: Network Policy)
    │               └── Phase 9 (US7: Auth verification)
    └── Phase 10 (Polish)
```

### Parallel Opportunities

- **Phase 1**: T002, T003, T004 all in parallel (different files)
- **Phase 1 + Phase 3**: T008, T009, T010 (values files) in parallel after T007 is started
- **Phase 5 (US3)**: T014, T015, T016 in parallel after T013 (`__init__`) is complete (different methods, same file — coordinate)
- **Phase 7 (US5)**: T020 (backup script) and T021 (CronJob template) in parallel
- **Phase 10 (Polish)**: T024, T025, T026, T027 all in parallel

---

## Parallel Example: Phase 5 (US3 — Upsert/Search)

```
# Sequential: T013 (__init__) must complete first

# Parallel group after T013:
Task T014: upsert_vectors method
Task T015: search_vectors method
Task T016: delete_vectors method

# Sequential after T014, T015, T016:
Task T017: get_collection_info + health_check
Task T018: integration test (uses all methods above)
```

---

## Implementation Strategy

### MVP (User Stories 1–4 Only)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T006)
3. Complete Phase 3: US1 — Cluster (T007–T011)
4. Complete Phase 4: US2 — Collections (T012)
5. Complete Phase 5: US3 — Upsert/Search (T013–T018)
6. Complete Phase 6: US4 — Latency SLA (T019)
7. **STOP and VALIDATE**: All P1 stories testable; semantic search working end-to-end

### Incremental Delivery

After MVP:
1. Add US5 (Backup) → 2 tasks → test snapshot + upload
2. Add US6 (Network policy) → 1 task → test namespace isolation
3. Add US7 (Auth) → 1 task → verify key enforcement
4. Polish → quality gates

---

## Notes

- [P] tasks use different files with no dependencies on incomplete tasks
- `helm dependency update deploy/helm/qdrant` must run before `helm install` to download the Qdrant sub-chart
- Integration tests require either a running Qdrant instance or `testcontainers` Qdrant image (`qdrant/qdrant`)
- The collection init script (`init_qdrant_collections.py`) is idempotent — safe to re-run; second run reports "already exists"
- `workspace_filter()` is a mandatory convention for multi-tenant collections — the `AsyncQdrantClient` wrapper does NOT enforce this at runtime (that would require knowing which collections are multi-tenant); developers must call `workspace_filter()` themselves
- Backup CronJob (T021) depends on both the Qdrant API key secret AND the MinIO credentials secret — both must be present before the CronJob runs
- Feature 004 (minio-object-storage) must be deployed before the backup CronJob can successfully upload snapshots
- Qdrant has no operator — StatefulSet deployment via official Helm chart is both the standard and recommended approach (documented in spec Assumptions)
