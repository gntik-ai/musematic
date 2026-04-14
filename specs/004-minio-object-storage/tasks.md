# Tasks: S3-Compatible Object Storage

**Input**: Design documents from `specs/004-minio-object-storage/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory scaffolding and add dependencies before any story work begins.

- [X] T001 Create `deploy/helm/minio/` directory and all subdirectories (`templates/`)
- [X] T002 [P] Add `aioboto3` to `apps/control-plane/pyproject.toml` under `[project.dependencies]`
- [X] T003 [P] Add `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_USE_SSL` settings to `apps/control-plane/src/platform/common/config.py` with defaults (`http://musematic-minio.platform-data:9000`, empty strings, `False`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Exception classes and shared data types used by all Python S3 operations.

**⚠️ CRITICAL**: No user story work on the Python client can begin until this phase is complete.

- [X] T004 Add `ObjectStorageError`, `ObjectNotFoundError`, `BucketNotFoundError` exception classes to `apps/control-plane/src/platform/common/exceptions.py`
- [X] T005 [P] Define `ObjectInfo` and `ObjectVersion` frozen dataclasses in `apps/control-plane/src/platform/common/clients/object_storage.py` — `ObjectInfo(key, size, last_modified, etag)`, `ObjectVersion(version_id, key, size, last_modified, is_latest)`; leave `AsyncObjectStorageClient` as a stub class for now

**Checkpoint**: Shared types and exceptions ready — all user story phases can now begin.

---

## Phase 3: User Story 1 — Platform Operator Deploys Object Storage Cluster (Priority: P1) 🎯 MVP

**Goal**: A production-ready 4-node erasure-coded MinIO cluster or single-node dev deployment, deployable via a single Helm command.

**Independent Test**: `helm install musematic-minio deploy/helm/minio -n platform-data -f values.yaml -f values-prod.yaml` completes; `kubectl wait tenant/musematic-minio --for=condition=Initialized -n platform-data` succeeds; all 4 server pods report ready.

- [X] T006 [US1] Create `deploy/helm/minio/Chart.yaml` with `apiVersion: v2`, `name: musematic-minio`, `version: 0.1.0`, `description: MinIO S3-compatible object storage for Musematic platform` — **no `dependencies` block** (MinIO operator is a cluster prerequisite, not a chart sub-dependency)
- [X] T007 [P] [US1] Create `deploy/helm/minio/values.yaml` with shared defaults: `clusterName: musematic-minio`, `namespace: platform-data`, `standalone: false`, `servers: 4`, `volumesPerServer: 4`, `storageClass: standard`, `storageSize: 100Gi`, `consoleEnabled: true`, `networkPolicy.enabled: true`, `buckets.executionArtifactsRetentionDays: 90`
- [X] T008 [P] [US1] Create `deploy/helm/minio/values-prod.yaml` with production overrides: `standalone: false`, `servers: 4`, `volumesPerServer: 4`, `storageSize: 100Gi`, `resources.requests.memory: 4Gi`, `resources.requests.cpu: "1"`, `networkPolicy.enabled: true`
- [X] T009 [P] [US1] Create `deploy/helm/minio/values-dev.yaml` with development overrides: `standalone: true`, `servers: 1`, `volumesPerServer: 1`, `storageSize: 10Gi`, `networkPolicy.enabled: false`, `resources.requests.memory: 512Mi`
- [X] T010 [US1] Create `deploy/helm/minio/templates/tenant.yaml` — `Tenant` CR (`minio.min.io/v2`): `spec.pools[0].servers: {{ .Values.servers }}`, `spec.pools[0].volumesPerServer: {{ .Values.volumesPerServer }}`, `spec.pools[0].volumeClaimTemplate` using storage class and size from values; wrapped in `{{- if not .Values.standalone }}`
- [X] T011 [P] [US1] Create `deploy/helm/minio/templates/deployment.yaml` — standalone `Deployment` for dev: single-replica MinIO container in filesystem mode, mounting a PVC at `/data`, environment variables `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from root credentials secret; wrapped in `{{- if .Values.standalone }}`
- [X] T012 [P] [US1] Create `deploy/helm/minio/templates/pvc.yaml` — single `PersistentVolumeClaim` for dev standalone, size from `values.storageSize`, storage class from `values.storageClass`; wrapped in `{{- if .Values.standalone }}`
- [X] T013 [P] [US1] Create `deploy/helm/minio/templates/secret-root.yaml` — `Secret` named `minio-root-credentials` with `MINIO_ROOT_USER: admin` and `MINIO_ROOT_PASSWORD: {{ randAlphaNum 32 | b64enc }}` (generated once at install, stable across upgrades via lookup)

**Checkpoint**: `helm lint deploy/helm/minio` passes; `helm template deploy/helm/minio -f values.yaml -f values-prod.yaml | grep "kind: Tenant"` outputs a valid CR; `helm template ... -f values-dev.yaml | grep "kind: Deployment"` outputs a valid Deployment.

---

## Phase 4: User Story 2 — Platform Creates All Required Buckets with Lifecycle Policies (Priority: P1)

**Goal**: All 8 buckets created with correct lifecycle policies (indefinite, 30d, 90d) and versioning on `agent-packages`, provisioned automatically as a post-install Helm hook.

**Independent Test**: After `helm install`, `kubectl wait job/musematic-minio-bucket-init --for=condition=Complete -n platform-data` succeeds; `mc ls local` returns 8 buckets; `mc ilm rule ls local/sandbox-outputs` shows a 30-day expiry rule; `mc version info local/agent-packages` shows versioning enabled.

- [X] T014 [US2] Create `deploy/helm/minio/templates/bucket-init-configmap.yaml` — `ConfigMap` containing an `init-buckets.sh` shell script that: (1) waits for MinIO to be ready with `mc alias set`; (2) creates all 8 buckets with `mc mb --ignore-existing`: `agent-packages`, `execution-artifacts`, `reasoning-traces`, `sandbox-outputs`, `evidence-bundles`, `simulation-artifacts`, `backups`, `forensic-exports`; (3) applies lifecycle rules with `mc ilm rule add`: `execution-artifacts` and `reasoning-traces` and `forensic-exports` with `--expire-days 90`; `sandbox-outputs`, `simulation-artifacts`, `backups` with `--expire-days 30`; all buckets with `--expire-days 7 --incomplete` for multipart cleanup; (4) enables versioning on `agent-packages` with `mc version enable`; (5) creates simulation user and attaches policy restricting to `simulation-artifacts` bucket only
- [X] T015 [US2] Create `deploy/helm/minio/templates/bucket-init-job.yaml` — `Job` with `helm.sh/hook: post-install,post-upgrade` and `helm.sh/hook-weight: "1"` annotations; runs the `init-buckets.sh` script from the ConfigMap using the `minio/mc` container image; reads `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from `minio-root-credentials` secret as environment variables; `restartPolicy: OnFailure`
- [X] T016 [US2] Create `deploy/helm/minio/templates/secret-platform.yaml` — `Secret` named `minio-platform-credentials` with `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` for the platform service user (credentials match what the init script creates for the platform IAM user)
- [X] T017 [US2] Create `deploy/helm/minio/templates/secret-simulation.yaml` — `Secret` named `minio-simulation-credentials` with `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` for the simulation IAM user (restricted to `simulation-artifacts` bucket)

**Checkpoint**: Deploy to a cluster with MinIO operator pre-installed; `kubectl logs job/musematic-minio-bucket-init -n platform-data` shows no errors; all 8 buckets confirmed via `mc ls`.

---

## Phase 5: User Story 3 — Services Store and Retrieve Objects via S3 API (Priority: P1)

**Goal**: Python services can upload, download, list, delete objects and perform multipart uploads (≥1 GB) using `AsyncObjectStorageClient`.

**Independent Test**: Run `apps/control-plane/tests/integration/test_object_storage_basic.py` using testcontainers MinIO — upload 1 KB object (checksum match), upload 1 GB via multipart (checksum match), list with prefix filter, delete and verify 404.

- [X] T018 [US3] Implement `AsyncObjectStorageClient.__init__` and `upload_object` in `apps/control-plane/src/platform/common/clients/object_storage.py` using `aioboto3.Session().client("s3")` — constructor reads `settings.MINIO_ENDPOINT`, `settings.MINIO_ACCESS_KEY`, `settings.MINIO_SECRET_KEY`, `settings.MINIO_USE_SSL`; configures `endpoint_url`, `aws_access_key_id`, `aws_secret_access_key`, `region_name="us-east-1"`; `upload_object` uses `s3.put_object(Bucket, Key, Body, ContentType)`, wraps `ClientError` in `ObjectStorageError` / `BucketNotFoundError`
- [X] T019 [US3] Implement `download_object`, `delete_object`, `object_exists` methods in `apps/control-plane/src/platform/common/clients/object_storage.py` — `download_object` uses `s3.get_object` and reads `Body`, raises `ObjectNotFoundError` on `NoSuchKey`; `delete_object` uses `s3.delete_object` (no-op if not found); `object_exists` uses `s3.head_object`, returns `False` on `404` without raising
- [X] T020 [US3] Implement `list_objects` method in `apps/control-plane/src/platform/common/clients/object_storage.py` — uses `s3.list_objects_v2(Bucket, Prefix, MaxKeys)`, returns `list[ObjectInfo]` with `key`, `size`, `last_modified`, `etag` populated from response `Contents`; raises `BucketNotFoundError` on `NoSuchBucket`
- [X] T021 [US3] Implement `upload_multipart` method in `apps/control-plane/src/platform/common/clients/object_storage.py` — initiates multipart upload with `create_multipart_upload`, reads `file_path` in chunks of `part_size_mb` MB, uploads each chunk with `upload_part`, completes with `complete_multipart_upload`; on any exception calls `abort_multipart_upload` before re-raising as `ObjectStorageError`
- [X] T022 [US3] Implement `get_presigned_url` and `health_check` methods in `apps/control-plane/src/platform/common/clients/object_storage.py` — `get_presigned_url` uses `s3.generate_presigned_url(ClientMethod, Params, ExpiresIn)`; `health_check` calls `s3.list_buckets()` and returns `{"status": "ok", "bucket_count": len(buckets)}` or `{"status": "error", "error": str(e)}`
- [X] T023 [US3] Write integration test `apps/control-plane/tests/integration/test_object_storage_basic.py` using `testcontainers` MinIO container (or `MINIO_TEST_MODE` env var pointing to running MinIO): (1) upload 1 KB bytes object → download → assert content identical (md5 match); (2) upload 110 MB file via `upload_multipart` → download → assert md5 match; (3) `list_objects` with prefix → assert only matching keys returned; (4) `delete_object` → `object_exists` returns `False`; (5) `download_object` nonexistent key → `ObjectNotFoundError` raised

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_object_storage_basic.py -v` passes all 5 test cases.

---

## Phase 6: User Story 4 — Agent Package Versioning Preserves All Revisions (Priority: P2)

**Goal**: The `agent-packages` bucket retains all object versions; operators can list and retrieve any specific version.

**Independent Test**: Upload object with key `test/agent.tar.gz`, upload again with different content, call `get_object_versions` → assert 2 versions returned; retrieve each by `version_id` → assert content matches the respective upload.

- [X] T024 [US4] Implement `get_object_versions` method in `apps/control-plane/src/platform/common/clients/object_storage.py` — uses `s3.list_object_versions(Bucket, Prefix=key)`, maps `Versions` list to `list[ObjectVersion]` with `version_id`, `key`, `size`, `last_modified`, `is_latest` fields; raises `ObjectStorageError` if versioning not enabled (detect by checking response structure)
- [X] T025 [US4] Write integration test `apps/control-plane/tests/integration/test_object_storage_versioning.py`: (1) upload `agent-packages/test/v1.tar.gz` with content `b"version1"`, upload same key with `b"version2"` → `get_object_versions` returns 2 versions; (2) retrieve by `version_id` using `download_object(bucket, key, version_id=v.version_id)` for each version → assert content is `b"version1"` and `b"version2"` respectively; (3) delete current version → previous version still retrievable; note: `download_object` signature needs optional `version_id` parameter (add to T019 implementation)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_object_storage_versioning.py -v` passes all 3 test cases.

---

## Phase 7: User Story 5 — Simulation Artifacts Are Isolated from Production (Priority: P2)

**Goal**: `simulation-artifacts` bucket is accessible only via simulation credentials; platform credentials are denied access to it.

**Independent Test**: Using platform credentials, attempt `upload_object` to `simulation-artifacts` → `ObjectStorageError` (403); using simulation credentials, upload to `simulation-artifacts` → success; using simulation credentials, attempt upload to `execution-artifacts` → `ObjectStorageError` (403).

- [X] T026 [US5] Update `init-buckets.sh` script in `deploy/helm/minio/templates/bucket-init-configmap.yaml` to: (1) create a MinIO IAM policy `simulation-policy` that allows `s3:*` on `simulation-artifacts/*` and `simulation-artifacts` bucket ARN only; (2) create a MinIO user `simulation` with a generated password; (3) attach `simulation-policy` to the `simulation` user; (4) create a MinIO IAM policy `platform-policy` that allows `s3:*` on all buckets EXCEPT `simulation-artifacts`; (5) create a MinIO user `platform` and attach `platform-policy` — all via `mc admin user add`, `mc admin policy create`, `mc admin policy attach`
- [X] T027 [US5] Write integration test `apps/control-plane/tests/integration/test_object_storage_isolation.py`: (1) using platform credentials, upload to `simulation-artifacts` → assert `ObjectStorageError` raised; (2) using simulation credentials (separate `AsyncObjectStorageClient` instance), upload to `simulation-artifacts` → assert success; (3) using simulation credentials, list `execution-artifacts` → assert `BucketNotFoundError` or `ObjectStorageError` raised; (4) verify no simulation objects appear in `list_objects("execution-artifacts")` result

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_object_storage_isolation.py -v` passes all 4 test cases.

---

## Phase 8: User Story 6 — Network Access Is Restricted to Authorized Namespaces (Priority: P2)

**Goal**: S3 API (port 9000) accessible from `platform-control` and `platform-execution` only; console (port 9001) accessible from `platform-observability` only; all other namespaces blocked.

**Independent Test**: Deploy with `networkPolicy.enabled: true`; `kubectl run` test pod in `platform-control` and confirm `mc ls` succeeds; `kubectl run` test pod in `default` and confirm connection times out.

- [X] T028 [US6] Create `deploy/helm/minio/templates/network-policy.yaml` — two `NetworkPolicy` resources wrapped in `{{- if .Values.networkPolicy.enabled }}`:
  (1) **s3-client-access**: `podSelector: {matchLabels: {app: minio}}` allows ingress on port 9000 from `namespaceSelector` matching `kubernetes.io/metadata.name: platform-control` OR `platform-execution` OR `platform-simulation` (three separate `from` entries with `namespaceSelector`);
  (2) **console-and-metrics-access**: same `podSelector` allows ingress on port 9000 (metrics scrape) and port 9001 (console) from `namespaceSelector` matching `kubernetes.io/metadata.name: platform-observability`

**Checkpoint**: `helm template deploy/helm/minio -f values.yaml -f values-prod.yaml | grep "kind: NetworkPolicy" | wc -l` outputs 2; `helm template ... -f values-dev.yaml | grep "kind: NetworkPolicy"` outputs nothing.

---

## Phase 9: User Story 7 — Operator Monitors Storage Health and Usage (Priority: P2)

**Goal**: Storage metrics visible in monitoring stack within 60 seconds; management console accessible showing all 8 buckets and per-bucket metrics.

**Independent Test**: Port-forward port 9000; `curl http://localhost:9000/minio/v2/metrics/cluster` returns Prometheus-format metrics including `minio_cluster_nodes_online` and `minio_bucket_objects_count`; port-forward port 9001; confirm console lists 8 buckets.

- [X] T029 [US7] Verify the `Tenant` CR in `deploy/helm/minio/templates/tenant.yaml` has `spec.prometheusOperator: false` set (MinIO serves its own metrics at `/minio/v2/metrics/cluster` on port 9000 without a separate exporter — no additional configuration needed); add a `Service` resource comment in `tenant.yaml` confirming `musematic-minio` service exposes port 9000 and `musematic-minio-console` service exposes port 9001 — these are created automatically by the MinIO Operator
- [X] T030 [US7] Add `health_check` invocation to the platform-cli diagnose command — in `apps/control-plane/src/platform/common/clients/object_storage.py`, confirm `health_check()` returns `{"status": "ok", "bucket_count": N}` (already implemented in T022); document in a comment that the expected `bucket_count` is 8 and any deviation should be flagged

**Checkpoint**: `curl http://localhost:9000/minio/v2/metrics/cluster | grep minio_cluster_nodes_online` returns a metric line; management console accessible at port 9001 showing 8 buckets.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, linting, type checking, Helm lint.

- [X] T031 [P] Run `helm lint deploy/helm/minio` and fix any linting errors — confirm no wildcard versions, no missing required fields, no stale template placeholders; verify `helm template` renders valid YAML for both prod and dev values
- [X] T032 [P] Run `ruff check apps/control-plane/src/platform/common/clients/object_storage.py` and fix any linting violations
- [X] T033 [P] Run `mypy apps/control-plane/src/platform/common/clients/object_storage.py` in strict mode and fix any type errors — pay special attention to `aioboto3` type stubs (may need `# type: ignore` for missing stubs with a comment explaining why)
- [X] T034 [P] Add `aioboto3` to `apps/control-plane/pyproject.toml` `[project.optional-dependencies]` under `[test]` group alongside `testcontainers[minio]` for integration test support

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks Python client user stories**
- **US1 (Phase 3)**: Depends on Phase 1 only — Helm chart, no Python dependency
- **US2 (Phase 4)**: Depends on US1 (bucket init Job needs the cluster to connect to)
- **US3 (Phase 5)**: Depends on Foundational (exceptions + types) and US2 (buckets must exist)
- **US4 (Phase 6)**: Depends on US3 (versioning requires working `download_object` with `version_id`)
- **US5 (Phase 7)**: Depends on US2 (IAM policy in init script) and US3 (client for testing)
- **US6 (Phase 8)**: Depends on US1 (network policy is part of cluster chart)
- **US7 (Phase 9)**: Depends on US1 (cluster must be running) and US2 (buckets must exist for console)
- **Polish (Phase 10)**: Depends on all phases complete

### User Story Dependencies

```
Phase 1 (Setup)
    ├── Phase 2 (Foundational: exceptions + data types)
    │       └── Phase 5 (US3: S3 Client → upload/download/list/delete)
    │               ├── Phase 6 (US4: Versioning)
    │               └── Phase 7 (US5: Simulation isolation test)
    └── Phase 3 (US1: Cluster)
            ├── Phase 4 (US2: Buckets + lifecycle + IAM)
            │       └── Phase 7 (US5: IAM policy in init script)
            ├── Phase 8 (US6: Network policy)
            └── Phase 9 (US7: Observability)
Phase 10 (Polish)
```

### Parallel Opportunities

Within each phase, tasks marked [P] can run simultaneously:
- **Phase 1**: T002, T003 run in parallel (different files)
- **Phase 3 (US1)**: T007, T008, T009 (values files) run in parallel; T011, T012, T013 run in parallel
- **Phase 5 (US3)**: T019, T020 run in parallel after T018 is complete (different methods, same file — coordinate carefully)
- **Phase 10 (Polish)**: T031, T032, T033, T034 all run in parallel

---

## Parallel Example: Phase 3 (US1 — Cluster)

```
# Parallel group 1 — values files (no dependencies on each other):
Task T007: Create values.yaml (shared defaults)
Task T008: Create values-prod.yaml (production overrides)
Task T009: Create values-dev.yaml (development overrides)

# Sequential: T010 (Tenant CR) before T011/T012/T013 (reference cluster name)

# Parallel group 2 — standalone resources (after T010 drafted):
Task T011: deployment.yaml (dev standalone)
Task T012: pvc.yaml (dev PVC)
Task T013: secret-root.yaml (root credentials)
```

---

## Implementation Strategy

### MVP (User Stories 1–3 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T005)
3. Complete Phase 3: US1 — Cluster (T006–T013)
4. Complete Phase 4: US2 — Buckets (T014–T017)
5. Complete Phase 5: US3 — S3 Client (T018–T023)
6. **STOP and VALIDATE**: All P1 stories independently testable and deployable

### Incremental Delivery

After MVP:
1. Add US4 (Versioning) → 2 tasks → test independently
2. Add US5 (Simulation isolation) → 2 tasks → test independently
3. Add US6 (Network policy) → 1 task → test independently
4. Add US7 (Observability) → 2 tasks → verify in running cluster
5. Polish phase → quality gates

---

## Notes

- [P] tasks use different files with no dependencies on incomplete tasks
- `helm lint` must pass before any cluster deployment attempt
- Integration tests require either a running MinIO instance or `testcontainers` MinIO image
- The `init-buckets.sh` script must be idempotent — `mc mb --ignore-existing` and `mc ilm rule add` with consistent IDs
- MinIO Operator must be pre-installed before `helm install` (see quickstart.md Prerequisites)
- The `secret-root.yaml` template uses Helm's `lookup` function to avoid regenerating credentials on upgrade: `{{ (lookup "v1" "Secret" .Release.Namespace "minio-root-credentials").data.MINIO_ROOT_PASSWORD | default (randAlphaNum 32 | b64enc) }}`
- The `standalone` deployment (dev) does not use the MinIO Operator at all — it is a plain Kubernetes `Deployment` running MinIO in single-node filesystem mode
- aioboto3 type stubs are incomplete; use `# type: ignore[assignment]` with comments where necessary
